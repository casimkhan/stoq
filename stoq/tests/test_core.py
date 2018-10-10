#!/usr/bin/env python3

#   Copyright 2014-2017 PUNCH Cyber Analytics Group
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import logging
import tempfile
import unittest
from unittest.mock import create_autospec, Mock

from stoq import PayloadMeta, RequestMeta, Stoq, StoqException
import stoq.tests.utils as utils


class TestCore(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.generic_content = b'The quick brown fox'

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_no_base_dir(self):
        # Verify that this doesn't throw an exception. Explicitly set log_dir
        # to none since we don't want to create logs in a random location and
        # shouldn't use a config file in this test.
        s = Stoq(log_dir=None)
        self.assertEqual(len(s.list_plugins()), 0)

    def test_config_from_base_dir(self):
        s = Stoq(base_dir=utils.get_data_dir())
        self.assertEqual(s.max_queue, 919)

    def test_file_log(self):
        with tempfile.TemporaryDirectory() as log_dir:
            # This verifies that the file handler logging doesn't throw an
            # exception, but we can't assert anything about contents because
            # we explcitly don't want to log things (to stdout) during tests
            Stoq(log_dir=log_dir)

    def test_initial_plugins(self):
        s = Stoq(
            base_dir=utils.get_data_dir(),
            providers=['dummy_provider'],
            archivers=['dummy_archiver'],
            connectors=['dummy_connector'],
            decorators=['dummy_decorator'],
            dispatchers=['dummy_dispatcher'],
            deep_dispatcher=['dummy_deep_dispatcher'])
        self.assertEqual(len(s._loaded_provider_plugins), 1)
        self.assertEqual(len(s._loaded_archiver_plugins), 1)
        self.assertEqual(len(s._loaded_connector_plugins), 1)
        self.assertEqual(len(s._loaded_decorator_plugins), 1)
        self.assertEqual(len(s._loaded_dispatcher_plugins), 1)
        self.assertEqual(len(s._loaded_deep_dispatcher_plugins), 1)

    ############ 'SCAN' TESTS ############

    def test_scan(self):
        s = Stoq(base_dir=utils.get_data_dir())
        response = s.scan(self.generic_content)
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].md5,
                         'a2004f37730b9445670a738fa0fc9ee5')

    def test_always_dispatch(self):
        s = Stoq(
            base_dir=utils.get_data_dir(), always_dispatch=['simple_worker'])
        response = s.scan(self.generic_content)
        self.assertIn('simple_worker', s._loaded_plugins)
        self.assertIn('simple_worker', response.results[0].plugins_run['workers'][0])
        self.assertIn('simple_worker', response.results[1].plugins_run['workers'][0])

    def test_start_dispatch(self):
        s = Stoq(base_dir=utils.get_data_dir())
        response = s.scan(
            self.generic_content, add_start_dispatch=['extract_random'])
        self.assertIn('extract_random', response.results[0].plugins_run['workers'][0])
        self.assertNotIn('extract_random', response.results[1].plugins_run['workers'][0])

    def test_dispatch(self):
        s = Stoq(
            base_dir=utils.get_data_dir(),
            dispatchers=['simple_dispatcher'])
        dummy_worker = s.load_plugin('dummy_worker')
        dummy_worker.scan = create_autospec(
            dummy_worker.scan, return_value=None)
        response = s.scan(self.generic_content)
        self.assertEqual(len(dummy_worker.scan.call_args[0]), 2)
        self.assertEqual(
            dummy_worker.scan.call_args[0][0].dispatch_meta['simple_dispatcher'],
            {'test_key': 'Useful metadata info'})
        self.assertIn('dummy_worker', response.results[0].plugins_run['workers'][0])

    def test_dispatch_duplicate(self):
        s = Stoq(
            base_dir=utils.get_data_dir(),
            dispatchers=['simple_dispatcher'])
        s.load_plugin('simple_dispatcher').WORKERS = ['simple_worker', 'simple_worker']
        simple_worker = s.load_plugin('simple_worker')
        simple_worker.scan = create_autospec(
            simple_worker.scan, return_value=None)
        s.scan(self.generic_content)
        self.assertEqual(simple_worker.scan.call_count, 1)
        self.assertEqual(len(simple_worker.scan.call_args[0]), 2)
        
    def test_dispatch_from_worker(self):
        s = Stoq(base_dir=utils.get_data_dir())
        simple_worker = s.load_plugin('simple_worker')
        simple_worker.DISPATCH_TO = ['extract_random']
        response = s.scan(self.generic_content, add_start_dispatch=['simple_worker'])
        self.assertIn('simple_worker', response.results[0].plugins['workers'])
        self.assertIn('extract_random', response.results[1].plugins['workers'])
        self.assertEqual('extract_random', response.results[2].extracted_by)

    def test_dispatch_multiple_rules(self):
        s = Stoq(
            base_dir=utils.get_data_dir(),
            dispatchers=['simple_dispatcher'])
        s.load_plugin('simple_dispatcher').WORKERS = ['simple_worker', 'simple_worker']
        simple_worker = s.load_plugin('simple_worker')
        simple_worker.scan = create_autospec(
            simple_worker.scan, return_value=None)
        s.scan(self.generic_content)
        self.assertEqual(simple_worker.scan.call_count, 1)
        self.assertEqual(len(simple_worker.scan.call_args[0]), 2)

    def test_dispatch_multiple_plugins(self):
        multi_plugin_content = b'multi-plugin-content'
        s = Stoq(
            base_dir=utils.get_data_dir(),
            dispatchers=['simple_dispatcher'])
        s.load_plugin('simple_dispatcher').WORKERS = ['simple_worker', 'dummy_worker']
        simple_worker = s.load_plugin('simple_worker')
        simple_worker.scan = create_autospec(
            simple_worker.scan, return_value=None)
        dummy_worker = s.load_plugin('dummy_worker')
        dummy_worker.scan = create_autospec(
            dummy_worker.scan, return_value=None)
        s.scan(multi_plugin_content)
        simple_worker.scan.assert_called_once()
        self.assertEqual(len(simple_worker.scan.call_args[0]), 2)
        dummy_worker.scan.assert_called_once()
        self.assertEqual(len(dummy_worker.scan.call_args[0]), 2)

    def test_dispatch_multiple_plugins2(self):
        again_multi_plugin_content = b'again-multi-plugin-space-content'
        s = Stoq(
            base_dir=utils.get_data_dir(),
            dispatchers=['simple_dispatcher'])
        s.load_plugin('simple_dispatcher').WORKERS = ['simple_worker', 'dummy_worker']
        simple_worker = s.load_plugin('simple_worker')
        simple_worker.scan = create_autospec(
            simple_worker.scan, return_value=None)
        dummy_worker = s.load_plugin('dummy_worker')
        dummy_worker.scan = create_autospec(
            dummy_worker.scan, return_value=None)
        s.scan(again_multi_plugin_content)
        simple_worker.scan.assert_called_once()
        self.assertEqual(len(simple_worker.scan.call_args[0]), 2)
        dummy_worker.scan.assert_called_once()
        self.assertEqual(len(dummy_worker.scan.call_args[0]), 2)

    def test_dispatch_nonexistent_plugin(self):
        s = Stoq(base_dir=utils.get_data_dir())
        response = s.scan(
            self.generic_content,
            add_start_dispatch=['this_plugin_doesnt_exist'])
        self.assertNotIn('this_plugin_doesnt_exist', response.results[0].plugins_run['workers'][0])
        self.assertEqual(len(response.errors), 1)

    def test_start_deep_dispatch(self):
        s = Stoq(base_dir=utils.get_data_dir())
        response = s.scan(
            self.generic_content, add_start_deep_dispatch=['extract_random'])
        self.assertIn('extract_random', response.results[0].plugins_run['workers'][1])
        self.assertNotIn('extract_random', response.results[0].plugins_run['workers'][0])

    def test_deep_dispatch(self):
        s = Stoq(
            base_dir=utils.get_data_dir(),
            deep_dispatchers=['simple_deep_dispatcher'])
        dummy_worker = s.load_plugin('dummy_worker')
        dummy_worker.scan = create_autospec(
            dummy_worker.scan, return_value=None)
        response = s.scan(self.generic_content)
        self.assertEqual(len(dummy_worker.scan.call_args[0]), 2)
        self.assertEqual(
            dummy_worker.scan.call_args[0][0].deep_dispatch_meta['simple_deep_dispatcher'],
            {'test_deep_key': 'Useful deep metadata info'})
        self.assertIn('dummy_worker', response.results[0].plugins_run['workers'][1])

    def test_deep_dispatch_duplicate(self):
        s = Stoq(
            base_dir=utils.get_data_dir(),
            deep_dispatchers=['simple_deep_dispatcher'])
        s.load_plugin('simple_deep_dispatcher').WORKERS = ['simple_worker', 'simple_worker']
        simple_worker = s.load_plugin('simple_worker')
        simple_worker.scan = create_autospec(
            simple_worker.scan, return_value=None)
        s.scan(self.generic_content)
        self.assertEqual(simple_worker.scan.call_count, 1)
        self.assertEqual(len(simple_worker.scan.call_args[0]), 2)

    def test_deep_dispatch_multiple_plugins(self):
        multi_plugin_content = b'multi-plugin-content'
        s = Stoq(
            base_dir=utils.get_data_dir(),
            deep_dispatchers=['simple_deep_dispatcher'])
        s.load_plugin('simple_deep_dispatcher').WORKERS = ['simple_worker', 'dummy_worker']
        simple_worker = s.load_plugin('simple_worker')
        simple_worker.scan = create_autospec(
            simple_worker.scan, return_value=None)
        dummy_worker = s.load_plugin('dummy_worker')
        dummy_worker.scan = create_autospec(
            dummy_worker.scan, return_value=None)
        s.scan(multi_plugin_content)
        simple_worker.scan.assert_called_once()
        self.assertEqual(len(simple_worker.scan.call_args[0]), 2)
        dummy_worker.scan.assert_called_once()
        self.assertEqual(len(dummy_worker.scan.call_args[0]), 2)

    def test_deep_dispatch_multiple_plugins2(self):
        again_multi_plugin_content = b'again-multi-plugin-space-content'
        s = Stoq(
            base_dir=utils.get_data_dir(),
            deep_dispatchers=['simple_deep_dispatcher'])
        s.load_plugin('simple_deep_dispatcher').WORKERS = ['simple_worker', 'dummy_worker']
        simple_worker = s.load_plugin('simple_worker')
        simple_worker.scan = create_autospec(
            simple_worker.scan, return_value=None)
        dummy_worker = s.load_plugin('dummy_worker')
        dummy_worker.scan = create_autospec(
            dummy_worker.scan, return_value=None)
        s.scan(again_multi_plugin_content)
        simple_worker.scan.assert_called_once()
        self.assertEqual(len(simple_worker.scan.call_args[0]), 2)
        dummy_worker.scan.assert_called_once()
        self.assertEqual(len(dummy_worker.scan.call_args[0]), 2)

    def test_deep_dispatch_nonexistent_plugin(self):
        s = Stoq(base_dir=utils.get_data_dir())
        response = s.scan(
            self.generic_content,
            add_start_deep_dispatch=['this_plugin_doesnt_exist'])
        self.assertNotIn('this_plugin_doesnt_exist', response.results[0].plugins_run['workers'][0])
        self.assertEqual(len(response.errors), 1)

    def test_archive(self):
        s = Stoq(base_dir=utils.get_data_dir(), archivers=['dummy_archiver'])
        dummy_archiver = s.load_plugin('dummy_archiver')
        dummy_archiver.archive = create_autospec(
            dummy_archiver.archive, return_value=None)
        response = s.scan(
            self.generic_content,
            request_meta=RequestMeta(archive_payloads=True))
        dummy_archiver.archive.assert_called_once()
        self.assertIn('dummy_archiver', response.results[0].plugins_run['archivers'])

    def test_dont_archive_request(self):
        s = Stoq(base_dir=utils.get_data_dir(), archivers=['dummy_archiver'])
        dummy_archiver = s.load_plugin('dummy_archiver')
        dummy_archiver.archive = Mock(return_value=None)
        response = s.scan(
            self.generic_content,
            add_start_dispatch=['extract_random'],
            request_meta=RequestMeta(archive_payloads=False))
        dummy_archiver.archive.assert_not_called()
        self.assertNotIn('dummy_archiver', response.results[0].plugins_run['archivers'])
        self.assertNotIn('dummy_archiver', response.results[1].plugins_run['archivers'])

    def test_dont_archive_payload(self):
        s = Stoq(base_dir=utils.get_data_dir(), archivers=['dummy_archiver'])
        dummy_archiver = s.load_plugin('dummy_archiver')
        dummy_archiver.archive = create_autospec(
            dummy_archiver.archive, return_value=None)
        response = s.scan(
            self.generic_content,
            payload_meta=PayloadMeta(should_archive=False),
            add_start_dispatch=['extract_random'],
            request_meta=RequestMeta(archive_payloads=True))
        dummy_archiver.archive.assert_called_once()
        self.assertNotIn('dummy_archiver', response.results[0].plugins_run['archivers'])
        self.assertIn('dummy_archiver', response.results[1].plugins_run['archivers'])

    def test_dont_archive_yara(self):
        s = Stoq(base_dir=utils.get_data_dir(), archivers=['dummy_archiver'])
        response = s.scan(
            self.generic_content,
            request_meta=RequestMeta(archive_payloads=True))
        # The yara rule 'similar_simple_rule' should set save = False
        self.assertNotIn('dummy_archiver', response.results[0].archivers)

    def test_worker_in_results(self):
        s = Stoq(base_dir=utils.get_data_dir())
        response = s.scan(
            self.generic_content, add_start_dispatch=['simple_worker'])
        self.assertIn('simple_worker', response.results[0].workers[0])
        self.assertIn('valuable_insight',
                      response.results[0].workers[0]['simple_worker'])

    def test_worker_not_in_results(self):
        s = Stoq(base_dir=utils.get_data_dir())
        response = s.scan(
            self.generic_content, add_start_dispatch=['dummy_worker'])
        self.assertNotIn('dummy_worker', response.results[0].workers)

    def test_archiver_in_results(self):
        s = Stoq(base_dir=utils.get_data_dir(), archivers=['simple_archiver'])
        response = s.scan(
            self.generic_content,
            request_meta=RequestMeta(archive_payloads=True))
        self.assertIn('simple_archiver', response.results[0].archivers)
        self.assertIn('file_save_id',
                      response.results[0].archivers['simple_archiver'])

    def test_archiver_not_in_results(self):
        s = Stoq(base_dir=utils.get_data_dir(), archivers=['dummy_archiver'])
        response = s.scan(
            self.generic_content,
            request_meta=RequestMeta(archive_payloads=True))
        self.assertNotIn('dummy_archiver', response.results[0].archivers)

    def test_worker_exception(self):
        s = Stoq(base_dir=utils.get_data_dir())
        simple_worker = s.load_plugin('simple_worker')
        simple_worker.RAISE_EXCEPTION = True
        response = s.scan(
            self.generic_content, add_start_dispatch=['simple_worker'])
        self.assertIn('simple_worker', response.results[0].plugins_run['workers'][0])
        self.assertEqual(len(response.errors), 1)
        self.assertIn('Test exception', response.errors[0])

    def test_worker_errors(self):
        s = Stoq(base_dir=utils.get_data_dir())
        simple_worker = s.load_plugin('simple_worker')
        simple_worker.RETURN_ERRORS = True
        response = s.scan(
            self.generic_content, add_start_dispatch=['simple_worker'])
        self.assertIn('simple_worker', response.results[0].plugins_run['workers'][0])
        self.assertIn('simple_worker', response.results[0].workers[0])
        self.assertEqual(len(response.errors), 1)
        self.assertIn('Test error', response.errors[0])

    def test_archiver_exception(self):
        s = Stoq(base_dir=utils.get_data_dir(), archivers=['simple_archiver'])
        simple_archiver = s.load_plugin('simple_archiver')
        simple_archiver.RAISE_EXCEPTION = True
        response = s.scan(self.generic_content)
        self.assertIn('simple_archiver', response.results[0].plugins_run['archivers'])
        self.assertEqual(len(response.errors), 1)
        self.assertIn('Test exception', response.errors[0])

    def test_archiver_errors(self):
        s = Stoq(base_dir=utils.get_data_dir(), archivers=['simple_archiver'])
        simple_archiver = s.load_plugin('simple_archiver')
        simple_archiver.RETURN_ERRORS = True
        response = s.scan(self.generic_content)
        self.assertIn('simple_archiver', response.results[0].plugins_run['archivers'])
        self.assertIn('simple_archiver', response.results[0].archivers)
        self.assertEqual(len(response.errors), 1)
        self.assertIn('Test error', response.errors[0])

    def test_max_recursion(self):
        max_rec_depth = 4  # defined in stoq.cfg
        s = Stoq(
            base_dir=utils.get_data_dir(), always_dispatch=['extract_random'])
        response = s.scan(self.generic_content)
        self.assertEqual(len(response.results), max_rec_depth + 1)

    def test_dedup(self):
        # The simple_worker plugin always extracts the same payload
        s = Stoq(
            base_dir=utils.get_data_dir(), always_dispatch=['simple_worker'])
        response = s.scan(self.generic_content)
        self.assertEqual(len(response.results), 2)

    def test_connector(self):
        s = Stoq(base_dir=utils.get_data_dir(), connectors=['dummy_connector'])
        dummy_connector = s.load_plugin('dummy_connector')
        dummy_connector.save = create_autospec(dummy_connector.save)
        s.scan(self.generic_content)
        dummy_connector.save.assert_called_once()

    def test_connector_exception(self):
        s = Stoq(base_dir=utils.get_data_dir(), connectors=['dummy_connector'])
        dummy_connector = s.load_plugin('dummy_connector')
        dummy_connector.save = create_autospec(
            dummy_connector.save,
            side_effect=RuntimeError('Unexpected exception'))
        with self.assertRaises(Exception):
            s.scan(self.generic_content)

    def test_decorator(self):
        s = Stoq(base_dir=utils.get_data_dir(), decorators=['simple_decorator'])
        _ = s.load_plugin('simple_decorator')
        response = s.scan(self.generic_content)
        self.assertIn('simple_decorator', response.decorators)
        self.assertIn('simple_decoration', response.decorators['simple_decorator'])

    def test_decorator_errors(self):
        s = Stoq(base_dir=utils.get_data_dir(), decorators=['simple_decorator'])
        simple_decorator = s.load_plugin('simple_decorator')
        simple_decorator.RETURN_ERRORS = True
        response = s.scan(self.generic_content)
        self.assertIn('simple_decorator', response.decorators)
        self.assertIn('simple_decoration', response.decorators['simple_decorator'])
        self.assertEqual(len(response.errors), 1)
        self.assertIn('Test error', response.errors[0])

    def test_decorator_exception(self):
        s = Stoq(base_dir=utils.get_data_dir(), decorators=['simple_decorator'])
        simple_decorator = s.load_plugin('simple_decorator')
        simple_decorator.RAISE_EXCEPTION = True
        response = s.scan(self.generic_content)
        self.assertEqual(len(response.errors), 1)
        self.assertIn('Test exception', response.errors[0])

    def test_multiclass_plugin(self):
        s = Stoq(
            base_dir=utils.get_data_dir(),
            dispatchers=['multiclass_plugin'])
        multiclass_worker = s.load_plugin('multiclass_plugin')
        multiclass_worker.scan = create_autospec(
            multiclass_worker.scan, return_value=None)
        response = s.scan(self.generic_content)
        self.assertEqual(len(multiclass_worker.scan.call_args[0]), 2)
        self.assertEqual(
            multiclass_worker.scan.call_args[0][0].dispatch_meta['multiclass_plugin']['multiclass_plugin']['rule0'],
            'multiclass_plugin')
        self.assertIn('multiclass_plugin', response.results[0].plugins_run['workers'][0])
        self.assertIn('multiclass_plugin', s._loaded_dispatcher_plugins)
        self.assertIn('multiclass_plugin', s._loaded_plugins)

    ############ 'RUN' TESTS ############

    def test_provider(self):
        s = Stoq(
            base_dir=utils.get_data_dir(),
            providers=['simple_provider'],
            connectors=['dummy_connector'])
        dummy_connector = s.load_plugin('dummy_connector')
        dummy_connector.save = create_autospec(dummy_connector.save)
        s.run()
        dummy_connector.save.assert_called_once()

    def test_no_providers(self):
        s = Stoq(base_dir=utils.get_data_dir())
        with self.assertRaises(StoqException):
            s.run()

    def test_multi_providers(self):
        s = Stoq(
            base_dir=utils.get_data_dir(),
            providers=['simple_provider', 'simple_provider2'],
            connectors=['dummy_connector'])
        dummy_connector = s.load_plugin('dummy_connector')
        dummy_connector.save = create_autospec(dummy_connector.save)
        s.run()
        self.assertEqual(dummy_connector.save.call_count, 2)

    def test_provider_exception(self):
        s = Stoq(base_dir=utils.get_data_dir(), providers=['simple_provider'])
        simple_provider = s.load_plugin('simple_provider')
        simple_provider.RAISE_EXCEPTION = True
        with self.assertRaises(StoqException):
            s.run()
