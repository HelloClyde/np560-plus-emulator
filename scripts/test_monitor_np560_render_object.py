import unittest

from scripts.monitor_np560_render_object import find_diagnostic, summarize


SAMPLE = (
    "NPE_RENDER_OBJECT=ACTIVE:0 BASE:0f7e CALLS:1 RETURNS:1 "
    "ENTRY:1b:2732/sp0e48/fp0fa6/arg0000:0f7e "
    "RETURN:02:1478>1b:2736/sp0e48/fp0fa6 "
    "CONTEXT:1/1@02:1478/wc620/sp0e48/fp0fa6/result0001/"
    "init0/branch1>18:d4ec/"
    "psw0001/r0000:0000/fail0@00:0000/"
    "tramp1@12:3456/wc620/sp0e44/fp0fa6/r0018 "
    "COMP:1@2f:2a6e/wbd13/sp0d00/fp0e42/"
    "child1@13:a5e8/wbd1c/sp0ce0/fp0e42/"
    "ret130@00:0000/w0000/sp0000/fp0000/"
    "src1@1c:2000>30:a5ec/wc620/sp0cce/fp0e42/r0018/"
    "stacka5ec,0030,0000,0000,0000,0000,0000,0000 "
    "BRANCH0:1/21:cff2>21:d184/psw0001/r00000 "
    "BRANCH1:1/21:d19c>21:d294/psw0001/r00000 "
    "LAYOUT:0 HELPER:1 "
    "INITIAL:00010203 BEFORE:00010204 AFTER:00000204 "
    "WRITES:2/2 TRACE:#1/I/1b:23c6/0fad(+2f)/0000>0001/8"
)


class RenderObjectMonitorTests(unittest.TestCase):
    def test_find_and_summarize(self) -> None:
        self.assertEqual(find_diagnostic("A=1\n" + SAMPLE + "\nB=2"), SAMPLE)
        summary = summarize(SAMPLE)
        self.assertIn("context calls/returns=1/1", summary)
        self.assertIn("from=02:1478/wc620/sp0e48/fp0fa6", summary)
        self.assertIn("branch=1>18:d4ec", summary)
        self.assertIn("context trampoline=1 from=12:3456", summary)
        self.assertIn("compositor entry=1@2f:2a6e", summary)
        self.assertIn("source=1@1c:2000>30:a5ec", summary)
        self.assertIn("diff initial>before: +03:03>04", summary)
        self.assertIn("diff before>after:  +01:01>00", summary)
        self.assertIn("writes total/retained=2/2", summary)


if __name__ == "__main__":
    unittest.main()
