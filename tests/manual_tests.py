import src.signia as sg
def func_a(a,b,c):
    return a + b + c
def func_b(d,e,f):
    return d * e + f


@sg.combine(func_a,func_b)
def wrapper(*args,**kwargs):
    print(func_a(**func_a.vars.unpack()))
    print(func_b(**func_b.vars.unpack()))

if __name__=='__main__':
    wrapper(1,2,3,4,5,6)