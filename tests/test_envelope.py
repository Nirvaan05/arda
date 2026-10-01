import unittest

from arda.envelope import AddressError, Message, parse, target


class EnvelopeTests(unittest.TestCase):
    def test_task_request_round_trips_and_tells_receiver_how_to_answer(self):
        message = Message(type='task_request', sender='@claude', recipient='@codex', body='Review the diff.\n')
        text = message.render('arda')
        self.assertTrue(text.startswith(f'[arda/1 task_request id={message.id} from=@claude to=@codex]\n'))
        self.assertIn(f'arda ack @claude {message.id}', text)
        self.assertIn(f'arda result @claude {message.id}', text)
        self.assertIn(f'arda reject @claude {message.id}', text)
        self.assertEqual(parse(text), Message(type='task_request', sender='@claude', recipient='@codex',
                                              body='Review the diff.', id=message.id))

    def test_replies_carry_the_request_id(self):
        for kind in ('ack', 'result', 'reject'):
            message = Message(type=kind, sender='@codex', recipient='@claude', body='x', re='abc123')
            text = message.render()
            self.assertIn(' re=abc123 ', text.splitlines()[0])
            self.assertEqual(parse(text).re, 'abc123')

    def test_reply_types_require_re_and_others_forbid_it(self):
        with self.assertRaises(ValueError):
            Message(type='ack', sender='@a', recipient='@b', body='x')
        with self.assertRaises(ValueError):
            Message(type='note', sender='@a', recipient='@b', body='x', re='abc123')
        with self.assertRaises(ValueError):
            Message(type='broadcast', sender='@a', recipient='@b', body='x')

    def test_body_lines_survive_and_footer_is_dropped(self):
        body = 'line one\n\n  [arda] quoted in the middle\nlast line'
        message = Message(type='note', sender='@a', recipient='@b', body=body)
        self.assertEqual(parse(message.render()).body, body)

    def test_non_arda_text_is_not_parsed(self):
        self.assertIsNone(parse('hello'))
        self.assertIsNone(parse('[arda/1 gossip id=1 from=@a to=@b]\nx'))
        self.assertIsNone(parse('[arda/1 note from=@a to=@b]\nmissing id'))

    def test_addresses(self):
        self.assertEqual(target('@codex'), 'codex')
        self.assertEqual(target('codex'), 'codex')
        self.assertEqual(target('w1:p2'), 'w1:p2')
        for bad in ('@Codex', '@', 'two words', '@-x', 'w1:t1'):
            with self.assertRaises(AddressError):
                target(bad)


if __name__ == '__main__':
    unittest.main()
