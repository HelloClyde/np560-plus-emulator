dmcu_ss = ss.source_set()
dmcu_system_ss = ss.source_set()
dmcu_system_ss.add(files('machine.c'))

dmcu_ss.add(files(
  'cpu.c',
  'clock.c',
  'disas.c',
  'dtu.c',
  'helper.c',
  'translate.c'))

target_arch += {'dmcu': dmcu_ss}
target_system_arch += {'dmcu': dmcu_system_ss}
