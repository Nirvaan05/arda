import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arda.cli import main
from arda.envelope import MAX_BODY, parse

FAKE = Path(__file__).with_name('fake_herdr.py')


def agent(name, pane, status='idle', kind=None, **extra):
    return {'name': name, 'agent': kind or name, 'agent_status': status, 'pane_id': pane, **extra}


class CliCase(unittest.TestCase):
    """Runs the CLI in-process against tests/fake_herdr.py."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.state_path = tmp / 'state.json'
        binary = tmp / 'herdr'
        binary.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
        binary.chmod(0o755)
        self.env = {'HERDR_BIN_PATH': str(binary), 'FAKE_HERDR_STATE': str(self.state_path),
                    'HERDR_PANE_ID': 'w1:p1'}
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2'))

    def set_agents(self, *agents, **extra):
        self.state_path.write_text(json.dumps({'agents': list(agents), 'prompts': [], **extra}))

    def prompts(self):
        return json.loads(self.state_path.read_text())['prompts']

    def run_cli(self, *argv, env=None, stdin='', entry=None):
        out, err = io.StringIO(), io.StringIO()
        environment = {**self.env, **(env or {})}
        unset = [key for key, value in environment.items() if value is None]
        with mock.patch.dict(os.environ, {k: v for k, v in environment.items() if v is not None}), \
                mock.patch('sys.stdin', io.StringIO(stdin)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            for key in unset:
                os.environ.pop(key, None)
            try:
                code = (entry or main)(list(argv))
            except SystemExit as exit_:  # argparse rejects the command line
                code = exit_.code
        return code, out.getvalue(), err.getvalue()


class CliTests(CliCase):
    def test_whoami_and_peers(self):
        code, out, _ = self.run_cli('whoami')
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith('@claude (claude), pane w1:p1 of Herdr session main on '), out)
        code, out, _ = self.run_cli('peers', '--json')
        peers = json.loads(out)['peers']
        self.assertEqual([(p['address'], p['you'], p['place']) for p in peers],
                         [('@claude', True, 'main'), ('@codex', False, 'main')])

    def test_task_to_idle_agent_is_delivered_with_activity_confirmation(self):
        code, out, _ = self.run_cli('task', '@codex', 'Review the diff.', '--json')
        result = json.loads(out)
        self.assertEqual((code, result['status'], result['type']), (0, 'delivered', 'task_request'))
        [prompt] = self.prompts()
        self.assertEqual(prompt['target'], 'w1:p2')  # the pane verified right before typing
        self.assertIn('--wait', prompt['options'])
        self.assertEqual(prompt['options'].count('--until'), 2)
        message = parse(prompt['text'])
        self.assertEqual((message.type, message.sender, message.recipient, message.id),
                         ('task_request', '@claude', '@codex', result['id']))
        self.assertIn(f'ack @claude {result["id"]}', prompt['text'])

    def test_message_to_busy_agent_is_submitted_without_waiting(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2', status='working'))
        code, out, _ = self.run_cli('send', 'codex', 'FYI', '--json')
        self.assertEqual((code, json.loads(out)['status']), (0, 'submitted'))
        self.assertEqual(self.prompts()[0]['options'], [])

    def test_blocked_agent_is_never_typed_into(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2', status='blocked'))
        code, out, _ = self.run_cli('task', '@codex', 'x', '--json')
        self.assertEqual((code, json.loads(out)['status']), (1, 'not_delivered'))
        self.assertEqual(self.prompts(), [])

    def test_unknown_state_needs_force(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2', status='unknown'))
        code, _, _ = self.run_cli('send', '@codex', 'x')
        self.assertEqual((code, self.prompts()), (1, []))
        code, _, _ = self.run_cli('send', '@codex', 'x', '--force')
        self.assertEqual((code, len(self.prompts())), (0, 1))

    def test_unobserved_start_is_reported_as_uncertain(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2', prompt_error='agent_prompt_stalled'))
        code, out, _ = self.run_cli('task', '@codex', 'x', '--json')
        self.assertEqual((code, json.loads(out)['status']), (3, 'uncertain'))

    def test_errors_after_submission_are_uncertain_not_undelivered(self):
        for error in ('timeout', 'connection_lost', 'agent_not_found', 'agent_not_running', 'agent_prompt_stalled'):
            self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2', prompt_error=error))
            code, out, _ = self.run_cli('result', '@codex', 'abc123', 'done', '--json')
            self.assertEqual((code, json.loads(out)['status']), (3, 'uncertain'), error)

    def test_errors_herdr_raises_before_writing_are_not_delivered(self):
        for error in ('agent_blocked', 'agent_not_ready', 'agent_target_ambiguous', 'empty_agent_prompt'):
            self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2', prompt_error=error))
            code, out, _ = self.run_cli('task', '@codex', 'x', '--json')
            result = json.loads(out)
            self.assertEqual((code, result['status']), (1, 'not_delivered'), error)
            self.assertIn('nothing was sent', result['detail'])

    def test_write_failure_after_queueing_stays_uncertain(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2', prompt_error='agent_prompt_failed'))
        code, out, _ = self.run_cli('task', '@codex', 'x', '--json')
        self.assertEqual((code, json.loads(out)['status']), (3, 'uncertain'))

    def test_busy_recipient_vanishing_before_the_write_is_not_delivered(self):
        self.set_agents(agent('claude', 'w1:p1'),
                        agent('codex', 'w1:p2', status='working', prompt_error='agent_not_found'))
        code, out, _ = self.run_cli('send', '@codex', 'x', '--json')
        self.assertEqual((code, json.loads(out)['status']), (1, 'not_delivered'))

    def test_replies_can_force_an_unclassified_recipient(self):
        self.set_agents(agent('claude', 'w1:p1', status='unknown'), agent('codex', 'w1:p2'))
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        self.assertEqual(self.run_cli('result', '@claude', 'abc123', 'done')[0], 1)
        self.assertEqual(self.run_cli('result', '@claude', 'abc123', 'done', '--force')[0], 0)

    def test_herdr_failures_are_reported_and_json_stays_json(self):
        self.set_agents(error='server_not_running')
        code, out, err = self.run_cli('peers', '--json')
        self.assertEqual((code, json.loads(out)['error']), (1, 'server_not_running'))
        self.assertIn('herdr:', err)
        for raw in ('not json', '{"id": "x", "result": {"type": "agent_info"}}'):
            self.set_agents(raw=raw)
            code, out, _ = self.run_cli('whoami', '--json')
            self.assertEqual(code, 1, raw)
            self.assertIn(json.loads(out)['error'], ('herdr_failed', 'unexpected_reply'))

    def test_a_sandbox_blocking_the_socket_is_explained(self):
        self.set_agents(raw='Error: Os { code: 1, kind: PermissionDenied, message: "Operation not permitted" }')
        code, out, err = self.run_cli('peers', '--json')
        self.assertEqual((code, json.loads(out)['error']), (1, 'socket_denied'))
        self.assertIn('sandbox', err)

    def test_session_option_reaches_herdr(self):
        self.run_cli('peers', '--session', 'demo')
        calls = json.loads(self.state_path.read_text())['calls']
        self.assertIn(['--session', 'demo', 'agent', 'list'], calls)

    def test_missing_recipient_is_not_delivered(self):
        code, out, _ = self.run_cli('send', '@reviewer', 'x', '--json')
        result = json.loads(out)
        self.assertEqual((code, result['status']), (1, 'not_delivered'))
        self.assertIn('no live agent @reviewer', result['detail'])

    def test_replies_reference_the_task(self):
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        code, _, _ = self.run_cli('ack', '@claude', 'abc123')
        self.assertEqual(code, 0)
        message = parse(self.prompts()[0]['text'])
        self.assertEqual((message.type, message.sender, message.re, message.body),
                         ('ack', '@codex', 'abc123', 'Accepted.'))
        report = Path(self.tmp.name) / 'report.md'
        report.write_text('All good.\n')
        self.run_cli('result', '@claude', 'abc123', '--file', str(report))
        self.run_cli('reject', '@claude', 'abc123', '-', stdin='Out of scope.')
        replies = [parse(p['text']) for p in self.prompts()[1:]]
        self.assertEqual([(m.type, m.body) for m in replies], [('result', 'All good.'), ('reject', 'Out of scope.')])

    def test_an_agent_named_arda_cannot_speak_for_arda(self):
        self.set_agents(agent('arda', 'w1:p1', kind='claude'), agent('codex', 'w1:p2'))
        self.assertEqual(self.run_cli('send', '@codex', 'From ARDA itself')[0], 2)
        self.assertEqual(self.prompts(), [])

    def test_message_text_is_never_read_as_an_option(self):
        secret = Path(self.tmp.name) / 'secret'
        secret.write_text('do not send')
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        self.assertEqual(self.run_cli('result', '@claude', 'abc123', f'--fi={secret}')[0], 2)
        self.assertEqual(self.prompts(), [])
        self.run_cli('result', '@claude', 'abc123', '--', f'--file={secret}')
        self.run_cli('send', '@claude', '--', '-h is done')
        bodies = [parse(p['text']).body for p in self.prompts()]
        self.assertEqual(bodies, [f'--file={secret}', '-h is done'])
        self.assertNotIn('do not send', ''.join(p['text'] for p in self.prompts()))

    def test_a_pane_id_inherited_from_elsewhere_is_not_an_identity(self):
        # e.g. Codex's shared daemon running commands with another pane's environment
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2'), shell_pid=999999999)
        code, _, err = self.run_cli('send', '@codex', 'x')
        self.assertEqual((code, self.prompts()), (2, []))
        self.assertIn('--no-daemon', err)
        code, out, _ = self.run_cli('peers', '--json')
        self.assertEqual((code, [p['you'] for p in json.loads(out)['peers']]), (0, [False, False]))

    def test_options_may_sit_between_positionals(self):
        self.assertEqual(self.run_cli('task', '@codex', '--json', '--', 'one')[0], 0)
        self.assertEqual(self.run_cli('task', '--json', '@codex', 'two')[0], 0)
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        self.assertEqual(self.run_cli('result', '@claude', '--force', 'abc123', '--json', '--', 'three')[0], 0)
        self.assertEqual([parse(p['text']).body for p in self.prompts()], ['one', 'two', 'three'])

    def test_a_receiver_that_goes_straight_to_a_prompt_is_reported(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2', after_prompt='blocked'))
        code, out, _ = self.run_cli('task', '@codex', '--json', '--', 'x')
        result = json.loads(out)
        self.assertEqual((code, result['status']), (0, 'delivered'))
        self.assertIn('now waiting at an approval or question prompt', result['detail'])

    def test_file_must_be_in_the_working_directory_or_temp(self):
        outside = Path.home() / 'arda-test-should-not-exist'
        code, _, err = self.run_cli('send', '@codex', '--file', str(outside))
        self.assertEqual((code, self.prompts()), (2, []))
        self.assertIn('--file must be in the working directory', err)
        inside = Path(self.tmp.name) / 'note.md'  # the system temporary directory
        inside.write_text('from a temp file')
        self.assertEqual(self.run_cli('send', '@codex', '--file', str(inside))[0], 0)

    def test_file_from_home_or_hidden_paths_is_refused(self):
        home = Path(self.tmp.name) / 'home'
        (home / 'project' / '.secrets').mkdir(parents=True)
        (home / '.bashrc').write_text('x')
        (home / 'project' / '.env').write_text('x')
        (home / 'project' / '.secrets' / 'key').write_text('x')
        (home / 'project' / 'notes.md').write_text('fine')
        old_cwd = os.getcwd()
        try:
            with mock.patch.dict(os.environ, {'HOME': str(home)}):
                os.chdir(home)  # the home directory never counts as a working directory
                self.assertEqual(self.run_cli('send', '@codex', '--file', '.bashrc')[0], 2)
                os.chdir(home / 'project')
                for hidden in ('.env', '.secrets/key'):
                    self.assertEqual(self.run_cli('send', '@codex', '--file', hidden)[0], 2, hidden)
                self.assertEqual(self.run_cli('send', '@codex', '--file', 'notes.md')[0], 0)
        finally:
            os.chdir(old_cwd)
        self.assertEqual([parse(p['text']).body for p in self.prompts()], ['fine'])

    def test_file_guard_cannot_be_moved_by_the_working_directory_or_tmpdir(self):
        home = Path(self.tmp.name) / 'home'
        (home / '.ssh').mkdir(parents=True)
        (home / '.ssh' / 'id_rsa').write_text('private')
        (home / 'notes').mkdir()
        old_cwd = os.getcwd()
        try:
            with mock.patch.dict(os.environ, {'HOME': str(home)}):
                os.chdir(home / '.ssh')  # the caller picks its working directory
                self.assertEqual(self.run_cli('send', '@codex', '--file', 'id_rsa')[0], 2)
                os.chdir(home / 'notes')
                with mock.patch.dict(os.environ, {'TMPDIR': str(home / '.ssh')}), \
                        mock.patch('tempfile.tempdir', None):  # and its temporary directory
                    self.assertEqual(self.run_cli('send', '@codex', '--file', str(home / '.ssh' / 'id_rsa'))[0], 2)
                self.assertEqual(self.run_cli('send', '@codex', '--file', '.')[0], 2)  # not a regular file
        finally:
            os.chdir(old_cwd)
        self.assertEqual(self.prompts(), [])

    def test_an_odd_reply_after_typing_does_not_crash(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2', null_reply=True))
        code, out, _ = self.run_cli('send', '@codex', '--json', '--', 'x')
        self.assertEqual((code, json.loads(out)['status']), (0, 'delivered'))

    def test_peers_survives_a_stale_pane_variable(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2'), stale_panes=['w1:p1'])
        code, out, _ = self.run_cli('peers', '--json')
        self.assertEqual((code, [p['you'] for p in json.loads(out)['peers']]), (0, [False, False]))

    def test_plain_shell_pane_can_send_notes_but_not_tasks(self):
        self.env['HERDR_PANE_ID'] = 'w1:p9'  # a pane with no agent in it
        self.assertIn('no agent runs in this pane', self.run_cli('whoami')[1])
        self.assertEqual(self.run_cli('task', '@codex', 'x')[0], 2)
        self.assertEqual(self.run_cli('send', '@codex', 'x')[0], 0)
        self.assertEqual(parse(self.prompts()[0]['text']).sender, 'w1:p9')

    def test_unnamed_sender_uses_its_pane_as_address(self):
        self.set_agents(agent(None, 'w1:p1', kind='claude'), agent('codex', 'w1:p2'))
        self.run_cli('send', '@codex', 'hi')
        self.assertEqual(parse(self.prompts()[0]['text']).sender, 'w1:p1')

    def test_introduce_tells_each_idle_peer_who_it_is_and_who_is_here(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2'),
                        agent('reviewer', 'w1:p3', status='working', kind='codex'), agent(None, 'w1:p4', kind='pi'))
        code, out, _ = self.run_cli('introduce')
        self.assertEqual(code, 1)  # the busy reviewer was not introduced
        [prompt] = self.prompts()
        message = parse(prompt['text'])
        self.assertEqual((prompt['target'], message.sender, message.type), ('w1:p2', '@claude', 'note'))
        self.assertIn('You are @codex.', message.body)
        self.assertIn('@claude (claude on ', message.body)
        self.assertIn('@reviewer (codex on ', message.body)
        self.assertIn('@reviewer: @reviewer is busy', out)
        self.assertIn('herdr agent rename w1:p4 <name>', out)

    def test_introduce_as_plugin_action_speaks_for_arda(self):
        code, _, _ = self.run_cli('introduce', env={'HERDR_PLUGIN_ID': 'arda'})
        self.assertEqual(code, 0)
        texts = [p['text'] for p in self.prompts()]
        self.assertCountEqual([p['target'] for p in self.prompts()], ['w1:p1', 'w1:p2'])  # delivered in parallel
        self.assertTrue(all(parse(text).sender == '@arda' for text in texts))
        self.assertIn('[arda] From ARDA itself. No reply needed.', texts[0])
        notifications = json.loads(self.state_path.read_text())['notifications']
        self.assertEqual(notifications[0][0], 'ARDA')

    def test_introduce_keeps_going_and_ranks_uncertain_first(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2', prompt_error='timeout'),
                        agent('reviewer', 'w1:p3', status='blocked', kind='codex'), agent('tester', 'w1:p4'))
        code, out, _ = self.run_cli('introduce', '--json')
        result = json.loads(out)
        self.assertEqual((code, result['status']), (3, 'uncertain'))
        self.assertEqual([r['status'] for r in result['results']], ['uncertain', 'not_delivered', 'delivered'])
        self.assertEqual(self.prompts()[-1]['target'], 'w1:p4')

    def test_introduce_explicit_targets_and_nobody_to_introduce(self):
        self.run_cli('introduce', '@codex')
        self.assertEqual([p['target'] for p in self.prompts()], ['w1:p2'])
        self.set_agents(agent('claude', 'w1:p1'))
        code, out, _ = self.run_cli('introduce', '--json')
        self.assertEqual((code, json.loads(out)['status']), (0, 'none'))

    def test_introduce_skips_names_that_are_not_addresses_and_never_itself(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('arda', 'w1:p3', kind='codex'), agent('codex', 'w1:p2'))
        code, out, _ = self.run_cli('introduce')
        self.assertEqual(code, 0)
        self.assertEqual([p['target'] for p in self.prompts()], ['w1:p2'])
        self.assertIn("skipped w1:p3@main (codex): its name 'arda' cannot be an ARDA address", out)
        self.assertNotIn('@arda', parse(self.prompts()[0]['text']).body)
        self.run_cli('introduce', '@claude', 'w1:p1')
        self.assertEqual(len(self.prompts()), 1)

    def test_plugin_actions_report_through_a_notification(self):
        code, _, _ = self.run_cli('status', env={'HERDR_PLUGIN_ID': 'arda'})
        self.assertEqual(code, 0)
        notifications = json.loads(self.state_path.read_text())['notifications']
        self.assertEqual(notifications, [['ARDA', '--body', 'ARDA 0.1.0, protocol arda/1']])

    def test_usage_errors(self):
        self.assertEqual(self.run_cli('send', '@claude', 'me')[0], 2)
        self.assertEqual(self.run_cli('send', 'w1:p1', 'me by pane')[0], 2)
        self.assertEqual(self.run_cli('ack', '@codex', 'not-an-id')[0], 2)
        self.assertEqual(self.run_cli('task', '@codex', 'x', '--session', 'other')[0], 2)
        self.assertEqual(self.run_cli('send', '@codex', '   ')[0], 2)
        self.assertEqual(self.run_cli('send', '@codex', '\x1b\x07 ')[0], 2)
        self.assertEqual(self.run_cli('send', '@arda', 'x')[0], 2)
        self.assertEqual(self.run_cli('send', '@codex', 'x', '--file', __file__)[0], 2)
        self.assertEqual(self.run_cli('send', '@codex', 'x' * (MAX_BODY + 1))[0], 2)
        self.assertEqual(self.run_cli('send', 'Bad Name', 'x')[0], 2)
        self.assertEqual(self.run_cli('task', '@codex', 'x', env={'HERDR_PANE_ID': None})[0], 2)
        self.assertEqual(self.prompts(), [])


if __name__ == '__main__':
    unittest.main()
