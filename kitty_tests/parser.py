#!/usr/bin/env python
# vim:fileencoding=utf-8
# License: GPL v3 Copyright: 2016, Kovid Goyal <kovid at kovidgoyal.net>

from functools import partial

from . import BaseTest

from kitty.fast_data_types import parse_bytes, parse_bytes_dump, CURSOR_BLOCK


class CmdDump(list):

    def __call__(self, *a):
        self.append(a)


class TestParser(BaseTest):

    def parse_bytes_dump(self, s, x, *cmds):
        cd = CmdDump()
        if isinstance(x, str):
            x = x.encode('utf-8')
        cmds = tuple(('draw', x) if isinstance(x, str) else x for x in cmds)
        parse_bytes_dump(cd, s, x)
        current = ''
        q = []
        for args in cd:
            if args[0] == 'draw':
                if args[1] is not None:
                    current += args[1]
            else:
                if current:
                    q.append(('draw', current))
                    current = ''
                q.append(args)
        if current:
            q.append(('draw', current))
        self.ae(tuple(q), cmds)

    def test_simple_parsing(self):
        s = self.create_screen()
        pb = partial(self.parse_bytes_dump, s)

        pb('12', '12')
        self.ae(str(s.line(0)), '12   ')
        self.ae(s.cursor.x, 2)
        pb('3456', '3456')
        self.ae(str(s.line(0)), '12345')
        self.ae(str(s.line(1)), '6    ')
        pb(b'\n123\n\r45', ('screen_linefeed',), '123', ('screen_linefeed',), ('screen_carriage_return',), '45')
        self.ae(str(s.line(1)), '6    ')
        self.ae(str(s.line(2)), ' 123 ')
        self.ae(str(s.line(3)), '45   ')
        parse_bytes(s, b'\rabcde')
        self.ae(str(s.line(3)), 'abcde')
        pb('\rßxyz1', ('screen_carriage_return',), 'ßxyz1')
        self.ae(str(s.line(3)), 'ßxyz1')
        pb('ニチ ', 'ニチ ')
        self.ae(str(s.line(4)), 'ニチ ')

    def test_esc_codes(self):
        s = self.create_screen()
        pb = partial(self.parse_bytes_dump, s)
        pb('12\033Da', '12', ('screen_index',), 'a')
        self.ae(str(s.line(0)), '12   ')
        self.ae(str(s.line(1)), '  a  ')
        pb('\033x', ('Unknown char after ESC: 0x%x' % ord('x'),))
        pb('\033c123', ('screen_reset', ), '123')
        self.ae(str(s.line(0)), '123  ')

    def test_charsets(self):
        s = self.create_screen()
        pb = partial(self.parse_bytes_dump, s)
        pb('\033)0\x0e/_', ('screen_designate_charset', 1, ord('0')), ('screen_change_charset', 1), '/_')
        self.ae(str(s.line(0)), '/\xa0   ')
        pb('\033%G_', ('screen_use_latin1', 0), '_')

    def test_csi_codes(self):
        s = self.create_screen()
        pb = partial(self.parse_bytes_dump, s)
        pb('abcde', 'abcde')
        s.cursor_back(5)
        pb('x\033[2@y', 'x', ('screen_insert_characters', 2), 'y')
        self.ae(str(s.line(0)), 'xy bc')
        pb('x\033[2;7@y', 'x', ('screen_insert_characters', 2), 'y')
        pb('x\033[@y', 'x', ('screen_insert_characters', 1), 'y')
        pb('x\033[345@y', 'x', ('screen_insert_characters', 345), 'y')
        pb('x\033[345;@y', 'x', ('screen_insert_characters', 345), 'y')
        pb('\033[H', ('screen_cursor_position', 1, 1))
        self.ae(s.cursor.x, 0), self.ae(s.cursor.y, 0)
        pb('\033[4H', ('screen_cursor_position', 4, 1))
        pb('\033[4;0H', ('screen_cursor_position', 4, 0))
        pb('\033[3;2H', ('screen_cursor_position', 3, 2))
        pb('\033[3;2;H', ('screen_cursor_position', 3, 2))
        pb('\033[00000000003;0000000000000002H', ('screen_cursor_position', 3, 2))
        self.ae(s.cursor.x, 1), self.ae(s.cursor.y, 2)
        pb('\033[J', ('screen_erase_in_display', 0, 0))
        pb('\033[?J', ('screen_erase_in_display', 0, 1))
        pb('\033[?2J', ('screen_erase_in_display', 2, 1))
        pb('\033[h')
        pb('\033[20;4h', ('screen_set_mode', 20, 0), ('screen_set_mode', 4, 0))
        pb('\033[?1000;1004h', ('screen_set_mode', 1000, 1), ('screen_set_mode', 1004, 1))
        pb('\033[20;4;20l', ('screen_reset_mode', 20, 0), ('screen_reset_mode', 4, 0), ('screen_reset_mode', 20, 0))
        s.reset()
        pb('\033[1;3;4;7;9;34;44m', ('select_graphic_rendition', '1 3 4 7 9 34 44 '))
        for attr in 'bold italic reverse strikethrough'.split():
            self.assertTrue(getattr(s.cursor, attr))
        self.ae(s.cursor.decoration, 1)
        self.ae(s.cursor.fg, 4 << 8 | 1)
        self.ae(s.cursor.bg, 4 << 8 | 1)
        pb('\033[38;5;1;48;5;7m', ('select_graphic_rendition', '38 5 1 48 5 7 '))
        self.ae(s.cursor.fg, 1 << 8 | 1)
        self.ae(s.cursor.bg, 7 << 8 | 1)
        pb('\033[38;2;1;2;3;48;2;7;8;9m', ('select_graphic_rendition', '38 2 1 2 3 48 2 7 8 9 '))
        self.ae(s.cursor.fg, 1 << 24 | 2 << 16 | 3 << 8 | 2)
        self.ae(s.cursor.bg, 7 << 24 | 8 << 16 | 9 << 8 | 2)
        pb('\033[;2m', ('select_graphic_rendition', '0 2 '))
        c = s.callbacks
        pb('\033[5n', ('report_device_status', 5, 0))
        self.ae(c.wtcbuf, b'\033[0n')
        c.clear()
        pb('\033[6n', ('report_device_status', 6, 0))
        self.ae(c.wtcbuf, b'\033[1;1R')
        pb('12345', '12345')
        c.clear()
        pb('\033[6n', ('report_device_status', 6, 0))
        self.ae(c.wtcbuf, b'\033[2;1R')
        pb('\033[2;4r', ('screen_set_margins', 2, 4))
        self.ae(s.margin_top, 1), self.ae(s.margin_bottom, 3)
        pb('\033[r', ('screen_set_margins', 0, 0))
        self.ae(s.margin_top, 0), self.ae(s.margin_bottom, 4)
        pb('\033[1 q', ('screen_set_cursor', 1, ord(' ')))
        self.assertTrue(s.cursor.blink)
        self.ae(s.cursor.shape, CURSOR_BLOCK)

    def test_osc_codes(self):
        s = self.create_screen()
        pb = partial(self.parse_bytes_dump, s)
        c = s.callbacks
        pb('a\033]2;xyz\x9cbcde', 'a', ('set_title', 'xyz'), 'bcde')
        self.ae(str(s.line(0)), 'abcde')
        self.ae(c.titlebuf, 'xyz')
        c.clear()
        pb('\033]\x07', ('set_title', ''), ('set_icon', ''))
        self.ae(c.titlebuf, ''), self.ae(c.iconbuf, '')
        pb('\033]ab\x07', ('set_title', 'ab'), ('set_icon', 'ab'))
        self.ae(c.titlebuf, 'ab'), self.ae(c.iconbuf, 'ab')
        c.clear()
        pb('\033]2;;;;\x07', ('set_title', ';;;'))
        self.ae(c.titlebuf, ';;;')
        pb('\033]110\x07', ('set_dynamic_color', ''))
        self.ae(c.colorbuf, '')

    def test_dcs_codes(self):
        s = self.create_screen()
        pb = partial(self.parse_bytes_dump, s)
        pb('a\033P+q436f\x9cbcde', 'a', ('screen_request_capabilities', '436f'), 'bcde')
        self.ae(str(s.line(0)), 'abcde')
