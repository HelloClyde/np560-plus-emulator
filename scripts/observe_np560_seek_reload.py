"""Read-only host hardware watches for the original MP3 reload path.

Imported by the owned-player probe. No guest breakpoints or memory writes;
debugger stops invalidate timing measurements. Four aligned hardware slots.
"""
import json
import subprocess

from probe_np560_code_write import HostWatch


def commands(pid):
    # Observe only the first reload's locals. Disable all watches at its
    # result store (portable across older GDB versions) so
    # later stack reuse is not mistaken for writes to a live reload frame.
    # Install the local watch only after the original reload function writes
    # its stream handle: R11 is then its live frame, not a guessed stack slot.
    local_commands = '''watch -l *(unsigned int *)($np->cpu->internal_data + $seek_fp - 4)
commands
silent
set $seek_hits = $seek_hits + 1
printf "SEEK_LOCAL writer=%06x pc=%06x fp=%04x watched_fp=%04x r0=%04x locals=%08x\\n", $env->current_instruction_pc, $env->pc, $env->gpr[11], $seek_fp, $env->gpr[0], *(unsigned int *)($np->cpu->internal_data + $seek_fp - 4)
if $env->gpr[11] == $seek_fp && ($env->current_instruction_pc == 0x22a036 || ($env->current_instruction_pc == 0x229d6e && $env->gpr[0] != 0))
printf "SEEK_FIRST_RESULT_CAPTURED\\n"
x/8hx $np->data.ram_block->host + 0x512840
disable
end
if $seek_hits >= 128
printf "SEEK_WRITE_LIMIT reached\\n"
disable
end
continue
end'''
    result = f'''set pagination off
set confirm off
set max-value-size unlimited
attach {pid}
set $np = (NP560MachineState *)current_machine
set $env = &$np->cpu->env
set $seek_fp = 0
set $seek_hits = 0
'''
    for name, address in (('stream', 0x512a16), ('file', 0x525468), ('header', 0x512848)):
        result += f'''watch -l *(unsigned int *)($np->data.ram_block->host + {address & ~3})
commands
silent
set $seek_hits = $seek_hits + 1
printf "SEEK_HANDLE name={name} writer=%06x pc=%06x fp=%04x r0=%04x r1=%04x\\n", $env->current_instruction_pc, $env->pc, $env->gpr[11], $env->gpr[0], $env->gpr[1]
x/4hx $np->data.ram_block->host + {address & ~3}
p/x $env->gpr
if $env->gpr[11] >= 0xb04 && $env->gpr[11] <= 0xfc0
x/32hx $np->cpu->internal_data + $env->gpr[11] - 4
end
if $seek_fp == 0 && ($env->current_instruction_pc == 0x229cc0 || $env->current_instruction_pc == 0x229ce8) && $env->gpr[11] >= 0xb04 && $env->gpr[11] <= 0xfc0 && ($env->gpr[11] & 3) == 0
set $seek_fp = $env->gpr[11]
python gdb.execute({json.dumps(local_commands)})
printf "SEEK_LOCAL_ARMED fp=%04x\\n", $seek_fp
end
if $seek_hits >= 128
printf "SEEK_WRITE_LIMIT reached\\n"
disable
end
continue
end
'''
    return result + 'printf "WATCH_READY guest_address=seek_reload\\n"\ncontinue\n'


class SeekReloadWatch(HostWatch):
    def __init__(self, qemu, pid, output):
        self.path = output / 'seek-reload-writes.log'
        self.log = self.path.open('x', encoding='utf-8')
        self.process = subprocess.Popen(
            ['gdb', '-q', '-nx', str(qemu)], stdin=subprocess.PIPE,
            stdout=self.log, stderr=subprocess.STDOUT, text=True)
        self.process.stdin.write(commands(pid))
        self.process.stdin.flush()

    def check(self):
        super().check()
        content = self.text()
        for error in ('Bad breakpoint number', 'Could not insert hardware watchpoint',
                      'No hardware breakpoint support', 'Error in sourced command file'):
            if error in content:
                raise RuntimeError('seek observer failed: ' + error)
