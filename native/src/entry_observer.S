// Original Win64 pre-entry observer, preserving flags, GPR arguments, all XMM
// registers and MXCSR. Continues through the exact original instruction bytes.
.intel_syntax noprefix
.text
.macro entry_shim index
.global DsrEntryObserverShim\index
.seh_proc DsrEntryObserverShim\index
DsrEntryObserverShim\index:
    pushfq
    .seh_stackalloc 8
    sub rsp,352
    .seh_stackalloc 352
    mov [rsp+296],r11
    mov [rsp+304],r10
    mov [rsp+312],r9
    mov [rsp+320],r8
    mov [rsp+328],rdx
    mov [rsp+336],rcx
    mov [rsp+344],rax
    movdqu [rsp+32],xmm0
    movdqu [rsp+48],xmm1
    movdqu [rsp+64],xmm2
    movdqu [rsp+80],xmm3
    movdqu [rsp+96],xmm4
    movdqu [rsp+112],xmm5
    movdqu [rsp+128],xmm6
    .seh_savexmm xmm6,128
    movdqu [rsp+144],xmm7
    .seh_savexmm xmm7,144
    movdqu [rsp+160],xmm8
    .seh_savexmm xmm8,160
    movdqu [rsp+176],xmm9
    .seh_savexmm xmm9,176
    movdqu [rsp+192],xmm10
    .seh_savexmm xmm10,192
    movdqu [rsp+208],xmm11
    .seh_savexmm xmm11,208
    movdqu [rsp+224],xmm12
    .seh_savexmm xmm12,224
    movdqu [rsp+240],xmm13
    .seh_savexmm xmm13,240
    movdqu [rsp+256],xmm14
    .seh_savexmm xmm14,256
    movdqu [rsp+272],xmm15
    .seh_savexmm xmm15,272
    .seh_endprologue
    stmxcsr [rsp+288]
    mov rcx,rsp
    mov edx,\index
    call DsrEntryObserverRecord
    ldmxcsr [rsp+288]
    movdqu xmm0,[rsp+32]
    movdqu xmm1,[rsp+48]
    movdqu xmm2,[rsp+64]
    movdqu xmm3,[rsp+80]
    movdqu xmm4,[rsp+96]
    movdqu xmm5,[rsp+112]
    movdqu xmm6,[rsp+128]
    movdqu xmm7,[rsp+144]
    movdqu xmm8,[rsp+160]
    movdqu xmm9,[rsp+176]
    movdqu xmm10,[rsp+192]
    movdqu xmm11,[rsp+208]
    movdqu xmm12,[rsp+224]
    movdqu xmm13,[rsp+240]
    movdqu xmm14,[rsp+256]
    movdqu xmm15,[rsp+272]
    mov r11,[rsp+296]
    mov r10,[rsp+304]
    mov r9,[rsp+312]
    mov r8,[rsp+320]
    mov rdx,[rsp+328]
    mov rcx,[rsp+336]
    mov rax,[rsp+344]
    add rsp,352
    popfq
    jmp QWORD PTR DsrEntryTrampolines[rip+8*\index]
.seh_endproc

.endm
entry_shim 0
entry_shim 1
entry_shim 2
entry_shim 3
entry_shim 4
entry_shim 5
entry_shim 6
entry_shim 7
