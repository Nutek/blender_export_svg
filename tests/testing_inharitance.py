class A:
    pass


class B(A):
    pass


class C:
    pass


print("C->A?", issubclass(C, A))
print("B->A?", issubclass(B, A))
print("A->A?", issubclass(A, A))
print("C->(C, A)?", issubclass(C, (C, A)))
