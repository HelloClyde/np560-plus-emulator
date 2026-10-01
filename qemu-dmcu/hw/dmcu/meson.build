dmcu_hw_ss = ss.source_set()
dmcu_hw_ss.add(when: 'CONFIG_NP560', if_true: files('np560.c', 'np560_timer.c', 'np560_audio.c', 'np560_nand_journal.c'))
dmcu_hw_ss.add(when: 'CONFIG_NP560', if_true: files('np560_mp3_codec.c', 'np560_mp3_hle.c', 'np560_npe_codec.c', 'np560_npe_hle.c', 'np560_eq.c'))
hw_arch += {'dmcu': dmcu_hw_ss}
