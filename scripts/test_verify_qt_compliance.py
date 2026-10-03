"""Regression checks for the public user guide's licence notice layouts."""
import unittest

from verify_qt_compliance import check_guide_notice


OPENING = 'Licence information and\nacknowledgements are in Appendix D .'
CONTENTS = 'Appendix D: Licences and acknowledgements 13\nQt . . . 13'
APPENDIX = '''Appendix D: Licences and acknowledgements
Hospital Roster System uses Qt 6.7.3 shared libraries.
Qt and its use are covered by the GNU Lesser General Public License version 3.
Qt is copyright The Qt Company Ltd. and other contributors.
The licence bundle contains the LGPL and GPL texts.
Qt_SOURCE_AVAILABILITY.txt gives the exact corresponding-source download.
Qt_BUILD_INSTRUCTIONS.txt explains how to rebuild and replace Qt.
'''


class GuideNoticeTests(unittest.TestCase):
    def test_original_opening_notice(self):
        self.assertEqual(check_guide_notice(['Uses Qt under LGPL version 3.']),
                         {'layout': 'opening_pages'})

    def test_signposted_appendix_after_opening_pages(self):
        self.assertEqual(check_guide_notice([CONTENTS, OPENING, 'Roster instructions', APPENDIX]),
                         {'layout': 'licence_appendix', 'page': 4})

    def test_appendix_continues_on_next_page(self):
        heading, notice = APPENDIX.split('\n', 1)
        self.assertEqual(check_guide_notice([CONTENTS, OPENING, heading, notice]),
                         {'layout': 'licence_appendix', 'page': 3})

    def test_contents_entry_does_not_replace_notice(self):
        with self.assertRaisesRegex(RuntimeError, 'appendix is missing'):
            check_guide_notice([CONTENTS, OPENING, 'Unrelated Qt and LGPL mentions'])

    def test_appendix_requires_opening_reference(self):
        with self.assertRaisesRegex(RuntimeError, 'appendix reference'):
            check_guide_notice([CONTENTS, 'Installation instructions', APPENDIX])

    def test_appendix_requires_substantive_notice(self):
        for fragment in ('uses Qt', 'GNU Lesser General Public License version 3',
                         'Qt is copyright The Qt Company', 'LGPL and GPL texts',
                         'corresponding-source download', 'rebuild and replace Qt'):
            with self.subTest(fragment=fragment):
                with self.assertRaisesRegex(RuntimeError, 'notice is incomplete'):
                    check_guide_notice([CONTENTS, OPENING, APPENDIX.replace(fragment, '')])


if __name__ == '__main__':
    unittest.main()
