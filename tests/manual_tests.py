import src.signia as sg
def func_a(a,b,c):
    return a + b + c
def func_b(d,e,f):
    return d * e + f

class StandardClass(object):
    def __init__(self):
        pass

    @sg.fuse(func_a,func_b)
    def wrapper(*args,**kwargs):
        pass

class BaseClass(object):
    def __init__(self):
        pass
    def base_func(self,a,b,c):
        return a+b+c

class ChildClass(BaseClass):
    @sg.fuse(BaseClass.base_func)
    def child_func(self,*args,**kwargs):
        return a*b+c

@sg.fuse(ChildClass.child_func,func_b)
def top_function(*args,**kwargs):
    print(a+b+c)
    print(func_b(func_b.vars.unpack()))

@sg.fuse(func_a)
def ext_func(new_input=0,*args,**kwargs):
    print(func_a(func_a.vars.unpack()))
    print(new_input)

@sg.fuse(func_a,func_b)
def wrapper(*args,**kwargs):
    print(func_a(func_a.vars.unpack()))
    print(func_b(func_b.vars.unpack()))

if __name__=='__main__':
    wrapper(1,2,3,4,5,6)
    cl=StandardClass()
    cl.wrapper(1,2,3,4,5,6)