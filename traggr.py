

import os
import re
import sys
import time
import logging
import traceback
import ConfigParser

from nose.exc import SkipTest
from nose.plugins import Plugin

from traggrcl import TRAggrAPIClient


log = logging.getLogger('nose.plugins.traggr')

RC_FILE_PATH = os.path.join(os.path.expanduser('~'), '.noserc')


class TRAggr(Plugin):

    name = 'traggr'

    def options(self, parser, env=os.environ):
        super(TRAggr, self).options(parser, env=env)

        # Read rc.
        config = ConfigParser.ConfigParser()
        config.read(RC_FILE_PATH)

        parser.add_option('--traggr-api-url', action='store', dest='traggr_api_url',
                          default=config.get('traggr', 'api_url')
                                  if config.has_option('traggr', 'api_url') else None,
                          help='Test Results Aggregation API URL. [default: %default]')

        parser.add_option('--traggr-project', action='store', dest='traggr_project',
                          default=config.get('traggr', 'project')
                                  if config.has_option('traggr', 'project') else None,
                          help='A project name, for which the results will be posted. [default: %default]')

        parser.add_option('--traggr-sprint', action='store', dest='traggr_sprint',
                          default=config.get('traggr', 'sprint')
                                  if config.has_option('traggr', 'sprint') else None,
                          help='A sprint name, for which the results will be posted. [default: %default]')

        parser.add_option('--traggr-component', action='store', dest='traggr_component',
                          default=config.get('traggr', 'component')
                                  if config.has_option('traggr', 'component') else None,
                          help='A component name, for which the results will be posted. [default: %default]')

        parser.add_option('--traggr-comment', action='store', dest='traggr_comment',
                          default=None,
                          help='A comment, which will be included into each test result.')

        parser.add_option('--traggr-test-attrs', action='store', dest='traggr_test_attrs',
                          default=config.get('traggr', 'test_attrs')
                                  if config.has_option('traggr', 'test_attrs') else None,
                          help='Test attributes, which will be included into each '
                               'test results if a test has such. [default: %default]')

        parser.add_option('--traggr-test-id-attr', action='store', dest='traggr_test_id_attr',
                          default=config.get('traggr', 'test_id_attr')
                                  if config.has_option('traggr', 'test_id_attr') else 'id',
                          help='Test attribute, used as a "test id". [default: %default]')

        parser.add_option('--traggr-verbose', action='store_true', dest='traggr_verbose',
                          default=False)

    def configure(self, options, conf):
        super(TRAggr, self).configure(options, conf)
        if not self.enabled:
            return

        # Check options.
        if not options.traggr_api_url:
            print('Please specify --traggr-api-url')
            sys.exit(1)

        if not options.traggr_project:
            print('Please specify --traggr-project')
            sys.exit(1)

        if not options.traggr_sprint:
            print('Please specify --traggr-sprint')
            sys.exit(1)

        if not options.traggr_component:
            print('Please specify --traggr-component')
            sys.exit(1)

        if options.traggr_verbose:
            log.setLevel(logging.DEBUG)

        self._sprint = options.traggr_sprint
        self._component = options.traggr_component
        self._project = options.traggr_project
        self._comment = options.traggr_comment
        self._test_attrs = options.traggr_test_attrs
        self._test_id_attr = options.traggr_test_id_attr
        if self._test_attrs:
            self._test_attrs = [attr.strip() for attr in self._test_attrs.split(',')]

        # Create a client and ping.
        self._client = TRAggrAPIClient(url=options.traggr_api_url)
        self._client.ping()

        self._results = []

    def _time_taken(self):
        """Calculate test execution time."""
        if hasattr(self, '_timer'):
            taken = time.time() - self._timer
        else:
            # Test died before it ran (probably error in setup())
            # or success/failure added before test started probably
            # due to custom TestResult munging
            taken = 0.0
        return taken

    def startTest(self, test):
        """Initializes a timer before starting a test."""
        self._timer = time.time()

    def _get_tb(self, tb):
        """Get a traceback."""

        # TODO: Not so good. Check this later.
        split_traceback = tb.split('-' * 20 +
               ' >> begin captured logging')[0].strip().split('\n')
        traceback_index = 0
        for index, line in enumerate(split_traceback):
            if line.startswith('    raise'):
                traceback_index = index + 1
                break

        traceback_ = split_traceback[traceback_index:]
        return '\n'.join(traceback_)

    def _get_test_method(self, test):

        return getattr(test.test, test.address()[2].split('.')[1])

    def _get_test_id(self, test):
        """Return a test id if present, else return an empty string."""
        try:
            method = self._get_test_method(test)
        except Exception, e:
            log.warning('Cannot get test method of test %s. Exception: %s' % (test, e))
            return ''

        try:
            # Get test attr "id".
            test_id = \
                getattr(method, self._test_id_attr, method.__name__)
            return test_id
        except Exception, e:
            log.warning('Cannot get test id of method %s. Exception: %s' % (method.__name__, e))
            return ''

    def _get_test_attributes(self, test):

        if not self._test_attrs:
            return

        try:
            method = self._get_test_method(test)
        except Exception, e:
            log.warning('Cannot get test method of test %s. Exception: %s' % (test, e))
            return None

        test_attributes = []

        for attr in self._test_attrs:
            attr_value = getattr(method, attr, None)
            if attr_value:
                if isinstance(attr_value, basestring):
                    test_attributes.append((attr, attr_value))
                elif isinstance(attr_value, (list, tuple)):
                    test_attributes += [(attr, value) for value in attr_value]
                else:
                    raise Exception('Do not know what to do with this test attr "%s". '
                                    'Method: %s.' % (attr, method))

        return test_attributes or None

    def _long_description(self, test):

        try:
            method = self._get_test_method(test)
        except Exception, e:
            log.warning('Cannot get test method of test %s. Exception: %s' % (test, e))
            return ''

        try:
            description = method.__doc__
            if not description:
                return ''

            description = description.split('\n', 1)[1]
            description = description.splitlines()

            # Cut it a little bit.
            min_num_leading_spaces = sys.maxint
            for line in description:
                if not line:
                    continue
                num_leading_spaces = len(line) - len(line.lstrip(' '))
                if num_leading_spaces < min_num_leading_spaces:
                    min_num_leading_spaces = num_leading_spaces

            if min_num_leading_spaces:

                cut_description = []
                regex = re.compile('^' + ' ' * min_num_leading_spaces)
                for line in description:
                    cut_description.append(re.sub(regex, '', line))
                description = cut_description

            description = '\n'.join(description)
            return description

        except Exception, e:
            log.warning('Cannot get test description of method %s. Exception: %s' % (method.__name__, e))
            return ''

    def _store_result(self, test_id, suite, title, description, result, error=None, test_attrs=None):

        # Ignore Nose failure results.
        if suite in ('suite', 'Failure'):
            return

        result = {'component': self._component,
                  'suite': suite,
                  'test_id': test_id,
                  'other_attributes': {'title': title,
                                       'description': description},
                  'result_attributes': {'result': result}}
        if error:
            result['result_attributes']['error'] = error

        if test_attrs:
            result['other_attributes']['attributes'] = test_attrs

        if self._comment:
            result['result_attributes']['comment'] = self._comment

        self._results.append(result)

    def addError(self, test, err, capt=None):
        """Prepare error for posting."""
        taken = self._time_taken()

        if issubclass(err[0], SkipTest):
            # Ignore skipped tests for now.
            return

        tb = ''.join(traceback.format_exception(*err))
        tb = self._get_tb(tb)
        test_id = self._get_test_id(test)
        self._store_result(test_id=test_id,
                           suite=test.id().split('.')[-2],
                           title=test.shortDescription(),
                           description=self._long_description(test),
                           result='error',
                           error=tb,
                           test_attrs=self._get_test_attributes(test))

    def addFailure(self, test, err, capt=None, tb_info=None):
        """Prepare failure for posting."""
        taken = self._time_taken()

        tb = ''.join(traceback.format_exception(*err))
        tb = self._get_tb(tb)
        test_id = self._get_test_id(test)

        self._store_result(test_id=test_id,
                           suite=test.id().split('.')[-2],
                           title=test.shortDescription(),
                           description=self._long_description(test),
                           result='failed',
                           error=tb,
                           test_attrs=self._get_test_attributes(test))

    def addSuccess(self, test, capt=None):
        """Prepare good result for posting."""
        taken = self._time_taken()
        test_id = self._get_test_id(test)

        self._store_result(test_id=test_id,
                           suite=test.id().split('.')[-2],
                           title=test.shortDescription(),
                           description=self._long_description(test),
                           result='passed',
                           test_attrs=self._get_test_attributes(test))

    def finalize(self, result):

        log.info('Posting results...')

        self._client.post_results(project=self._project,
                                  sprint=self._sprint,
                                  results=self._results)
        log.info('Done.')


# EOF
