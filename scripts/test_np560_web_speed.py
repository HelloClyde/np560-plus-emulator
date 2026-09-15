"""Fast Web mode must not change clocks or suppress full diagnostic APIs."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from web import np560_web as web


class WebSpeedTests(unittest.TestCase):
    def test_light_snapshot_retains_frame_and_skips_cpu_dump(self):
        emu = web.Emulator.__new__(web.Emulator)
        emu.process = Mock()
        emu.process.poll.return_value = None
        emu.qmp = Mock()
        emu.qmp.execute.side_effect = lambda cmd, args=None: (
            {'running':True, 'status':'running'} if cmd == 'query-status' else
            'test-' + args['property'])
        emu.nand_save_on_exit = None
        emu.soc_rom_size = 123
        emu.soc_rom_sha256 = 'test'
        full = emu.snapshot('lcd', 0, 0)
        emu.qmp.reset_mock()
        lite = emu.snapshot('lcd', 0, 0, diagnostics=False)
        self.assertIsNone(lite.pop('registers'))
        self.assertEqual(full.pop('registers'), 'test-cpu-state')
        self.assertEqual(lite, full)
        self.assertFalse(any(c.args[1].get('property') == 'cpu-state'
                             for c in emu.qmp.execute.call_args_list if len(c.args) > 1))

    def test_start_configures_observers_before_first_instruction(self):
        args = SimpleNamespace(**{k:None for k in ('qemu','firmware','mask_rom','soc_rom',
            'usb_loader','burn_code','driver_code','nand_image','nand_checkpoint','nand_save_on_exit')})
        args.__dict__.update(boot_mode='firmware-vma03', rom_hle=False, hle_ui=False,
            startup_context=0, adc_level=8, external_power=0, soc_rom_skeleton=True,
            log_unimp=False, icount_shift=None, debug_program_load=[],
            initial_key_matrix_low=0, initial_key_matrix_high=0)
        with patch.object(web, 'Emulator') as constructor:
            emu = web.start_emulator(args, None)
            self.assertTrue(constructor.call_args.kwargs['start_paused'])
            self.assertEqual(emu.qmp.execute.call_args_list[0].args,
                ('qom-set', {'path':'/machine','property':'control-observers-minimal','value':True}))
            self.assertEqual(emu.qmp.execute.call_args_list[-1].args, ('cont',))
            self.assertEqual(len(emu.qmp.execute.call_args_list), 2)


if __name__ == '__main__':
    unittest.main()
