.text
.globl guard_fixture
guard_fixture:
    pushq %rbx
    pushq %r15
    subq $0x98,%rsp
    movq %rdx,0x68(%rsp)
    movq %r8,0x70(%rsp)
    movq %r9,0x78(%rsp)
    leaq fixture_index(%rip),%r15
    xorq %rax,%rax
    stc
    jmp *%rcx
.globl guard_fixture_empty
guard_fixture_empty:
    pushfq
    popq %r10
    movl $1,%eax
    jmp finish
.globl guard_fixture_resume
guard_fixture_resume:
    pushfq
    popq %r10
    cmpq 0x68(%rsp),%rbx
    jne invalid
    cmpq (%rbx),%r9
    jne invalid
    cmpq $1234,%rcx
    jne invalid
    testq %r8,%r8
    jne invalid
    testq %rax,%rax
    jne invalid
    movl $2,%eax
    jmp finish
invalid:
    movl $3,%eax
finish:
    movq %r10,%rdx
    andq $1,%rdx
    shlq $32,%rdx
    orq %rdx,%rax
    addq $0x98,%rsp
    popq %r15
    popq %rbx
    ret
.data
.align 8
fixture_index:
    .quad 0
