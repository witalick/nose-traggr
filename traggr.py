
import os
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
                          default=config.get('traggr', 'url')
                                  if config.has_option('traggr', 'url') else None,
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
                          help='A component name, for which the results will be posted.')


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

        self._sprint = options.traggr_sprint
        self._component = options.traggr_component
        self._project = options.traggr_project

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
        return tb.split('-' * 20 +
               ' >> begin captured logging')[0].strip().split('\n')[-1]

    def _get_test_id(self, test):
        """Return a test id if present, else return an empty string."""
        try:
            method = getattr(test.test, test.address()[2].split('.')[1])

            # Get Nose attr "id".
            return getattr(method, 'id', method.__name__)
        except Exception:
            log.warning('Cannot get test id of %s' % method.__name__)
            return ''

    def _long_description(self, test):

        try:
            method = getattr(test.test, test.address()[2].split('.')[1])

            description = method.__doc__
            if description:
                return description.split('\n', 1)[1]

        except Exception:
            log.warning('Cannot get test description of %s' % method.__name__)

        return ''

    def _store_result(self, test_id, suite, title, description, result, error=None):

        result = {'component': self._component,
                  'suite': suite,
                  'test_id': test_id,
                  'other_attributes': {'title': title,
                                       'description': description},
                  'result_attributes': {'result': result}}
        if error:
            result['result_attributes']['error'] = error

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
                           error=tb)

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
                           error=tb)

    def addSuccess(self, test, capt=None):
        """Prepare good result for posting."""
        taken = self._time_taken()
        test_id = self._get_test_id(test)

        self._store_result(test_id=test_id,
                           suite=test.id().split('.')[-2],
                           title=test.shortDescription(),
                           description=self._long_description(test),
                           result='passed')

    def finalize(self, result):

        log.info('Posting results...')

        self._client.post_results(project=self._project,
                                  sprint=self._sprint,
                                  results=self._results)
        log.info('Done.')


# EOF
