dmcu_ss = ss.source_set()
dmcu_system_ss = ss.source_set()

dmcu_ss.add(files(
  'cpu.c',
  'disas.c',
  'helper.c',
  'translate.c'))

target_arch += {'dmcu': dmcu_ss}
target_system_arch += {'dmcu': dmcu_system_ss}
