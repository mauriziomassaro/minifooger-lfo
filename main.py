# Arbitrary waveform generator for Rasberry Pi Pico
# Requires 8-bit R2R DAC on pins specified. R=1kOhm
# Contrived by Rolf Oldeman, CC BY-NC-SA 4.0 licence, mod by winkelschleifer 9/21
from machine import Pin, mem32, ADC, PWM
from rp2 import PIO, StateMachine, asm_pio
from array import array
from utime import sleep
from math import pi,sin,exp,sqrt,floor
from uctypes import addressof
from random import random
import random
# peripherals
red = PWM(Pin(22))
green = PWM(Pin(21))
blue = PWM(Pin(20))
pot = ADC(26)
fsw = Pin(19, Pin.IN, Pin.PULL_DOWN)
temp = ADC(4)
tconv=3.3/65535

fclock=125000000 #clock frequency of the pico

DMA_BASE=0x50000000
CH0_READ_ADDR  =DMA_BASE+0x000
CH0_WRITE_ADDR =DMA_BASE+0x004
CH0_TRANS_COUNT=DMA_BASE+0x008
CH0_CTRL_TRIG  =DMA_BASE+0x00c
CH0_AL1_CTRL   =DMA_BASE+0x010
CH1_READ_ADDR  =DMA_BASE+0x040
CH1_WRITE_ADDR =DMA_BASE+0x044
CH1_TRANS_COUNT=DMA_BASE+0x048
CH1_CTRL_TRIG  =DMA_BASE+0x04c
CH1_AL1_CTRL   =DMA_BASE+0x050

PIO0_BASE      =0x50200000
PIO0_TXF0      =PIO0_BASE+0x10
PIO0_SM0_CLKDIV=PIO0_BASE+0xc8

#state machine that just pushes bytes to the pins
@asm_pio(out_init=(PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH),
         out_shiftdir=PIO.SHIFT_RIGHT, autopull=True, pull_thresh=32)
def stream():
    out(pins,8)

sm = StateMachine(0, stream, freq=125000000, out_base=Pin(8))
sm.active(1)

#2-channel chained DMA. channel 0 does the transfer, channel 1 reconfigures
p=array('I',[0]) #global 1-element array
def startDMA(ar,nword):
    #first disable the DMAs to prevent corruption while writing
    mem32[CH0_AL1_CTRL]=0
    mem32[CH1_AL1_CTRL]=0
    #setup first DMA which does the actual transfer
    mem32[CH0_READ_ADDR]=addressof(ar)
    mem32[CH0_WRITE_ADDR]=PIO0_TXF0
    mem32[CH0_TRANS_COUNT]=nword
    IRQ_QUIET=0x1 #do not generate an interrupt
    TREQ_SEL=0x00 #wait for PIO0_TX0
    CHAIN_TO=1    #start channel 1 when done
    RING_SEL=0
    RING_SIZE=0   #no wrapping
    INCR_WRITE=0  #for write to array
    INCR_READ=1   #for read from array
    DATA_SIZE=2   #32-bit word transfer
    HIGH_PRIORITY=1
    EN=1
    CTRL0=(IRQ_QUIET<<21)|(TREQ_SEL<<15)|(CHAIN_TO<<11)|(RING_SEL<<10)|(RING_SIZE<<9)|(INCR_WRITE<<5)|(INCR_READ<<4)|(DATA_SIZE<<2)|(HIGH_PRIORITY<<1)|(EN<<0)
    mem32[CH0_AL1_CTRL]=CTRL0
    #setup second DMA which reconfigures the first channel
    p[0]=addressof(ar)
    mem32[CH1_READ_ADDR]=addressof(p)
    mem32[CH1_WRITE_ADDR]=CH0_READ_ADDR
    mem32[CH1_TRANS_COUNT]=1
    IRQ_QUIET=0x1 #do not generate an interrupt
    TREQ_SEL=0x3f #no pacing
    CHAIN_TO=0    #start channel 0 when done
    RING_SEL=0
    RING_SIZE=0   #no wrapping
    INCR_WRITE=0  #single write
    INCR_READ=0   #single read
    DATA_SIZE=2   #32-bit word transfer
    HIGH_PRIORITY=1
    EN=1
    CTRL1=(IRQ_QUIET<<21)|(TREQ_SEL<<15)|(CHAIN_TO<<11)|(RING_SEL<<10)|(RING_SIZE<<9)|(INCR_WRITE<<5)|(INCR_READ<<4)|(DATA_SIZE<<2)|(HIGH_PRIORITY<<1)|(EN<<0)
    mem32[CH1_CTRL_TRIG]=CTRL1

def setupwave(buf,f,w):
    div=fclock/(f*maxnsamp) # required clock division for maximum buffer size
    if div<1.0:  #can't speed up clock, duplicate wave instead
        dup=int(1.0/div)
        nsamp=int((maxnsamp*div*dup+0.5)/4)*4 #force multiple of 4
        clkdiv=1
    else:        #stick with integer clock division only
        clkdiv=int(div)+1
        nsamp=int((maxnsamp*div/clkdiv+0.5)/4)*4 #force multiple of 4
        dup=1

    #fill the buffer
    for isamp in range(nsamp):
        buf[isamp]=max(0,min(255,int(256*eval(w,dup*(isamp+0.5)/nsamp))))

    #set the clock divider
    clkdiv_int=min(clkdiv,65535) 
    clkdiv_frac=0 #fractional clock division results in jitter
    mem32[PIO0_SM0_CLKDIV]=(clkdiv_int<<16)|(clkdiv_frac<<8)

    #start DMA
    startDMA(buf,int(nsamp/4))


#evaluate the content of a wave
def eval(w,x):
    m,s,p=1.0,0.0,0.0
    if 'phasemod' in w.__dict__:
        p=eval(w.phasemod,x)
    if 'mult' in w.__dict__:
        m=eval(w.mult,x)
    if 'sum' in w.__dict__:
        s=eval(w.sum,x)
    x=x*w.replicate-w.phase-p
    x=x-floor(x)  #reduce x to 0.0-1.0 range
    v=w.func(x,w.pars)
    v=v*w.amplitude*m
    v=v+w.offset+s
    return v

#some common waveforms. combine with sum,mult,phasemod
def sine(x,pars):
    return sin(x*2*pi)
def pulse(x,pars): #risetime,uptime,falltime
    if x<pars[0]: return x/pars[0]
    if x<pars[0]+pars[1]: return 1.0
    if x<pars[0]+pars[1]+pars[2]: return 1.0-(x-pars[0]-pars[1])/pars[2]
    return 0.0
def gaussian(x,pars):
    return exp(-((x-0.5)/pars[0])**2)
def sinc(x,pars):
    if x==0.5: return 1.0
    else: return sin((x-0.5)/pars[0])/((x-0.5)/pars[0])
def exponential(x,pars):
    return exp(-x/pars[0])
def noise(x,pars): #p0=quality: 1=uniform >10=gaussian
    return sum([random()-0.5 for _ in range(pars[0])])*sqrt(12/pars[0])
    

#make buffers for the waveform.
#large buffers give better results but are slower to fill
maxnsamp=2048 #must be a multiple of 4. miximum size is 65536
wavbuf={}
wavbuf[0]=bytearray(maxnsamp)
wavbuf[1]=bytearray(maxnsamp)
ibuf=0

sinemode=False
expomode=False
tonemode=False

#empty class just to attach properties to
class wave:
    pass

#mode 1: random
if sinemode==False:
    reading = temp.read_u16() * tconv 
    temperature = 27 - (reading - 0.706)/0.001721
    blue.duty_u16(12767)
    red.duty_u16(6000)
    green.duty_u16(5767)
    wave1=wave()
    wave1.offset=0.5
    wave1.phase=0.0
    wave1.replicate=1
    wave1.func=sine
    wave1.pars=[]
    while sinemode==False:
        if fsw.value()==1:
            sinemode=True        
        else:
            pval=((pot.read_u16())/4096)
            scope=(round(pval))+1
            randfreq=(temperature-random.randint(18,32)) / scope
            wave1.amplitude=0.5+random.random()
            setupwave(wavbuf[ibuf],randfreq,wave1); ibuf=(ibuf+1)%2
#mode 2: sine
if sinemode==True:
    blue.duty_u16(4000)
    red.duty_u16(10202)
    green.duty_u16(18202)
    wave1=wave()
    wave1.amplitude=0.5
    wave1.offset=0.5
    wave1.phase=0.0
    wave1.replicate=1
    wave1.func=sine
    wave1.pars=[]
    pval=(pot.read_u16())/4096
    freq=round(pval)+1
    setupwave(wavbuf[ibuf],freq,wave1); ibuf=(ibuf+1)%2
    while sinemode==True:
        if fsw.value()==1:
            sinemode=False
            expomode=True
        else:
            pval=(pot.read_u16())/4096
            nfreq=round(pval)+1
            if freq is not nfreq:
                freq=nfreq
                setupwave(wavbuf[ibuf],freq,wave1); ibuf=(ibuf+1)%2
#mode 3: exp x sine
if expomode==True:
    blue.duty_u16(25025)
    red.duty_u16(0)
    green.duty_u16(15025)     
    wave1=wave()
    wave1.amplitude=0.5
    wave1.offset=0.3
    wave1.phase=0.0
    wave1.replicate=5
    wave1.func=sine
    wave1.pars=[]

    wave2=wave()
    wave2.amplitude=1.0
    wave2.offset=0.0
    wave2.phase=0.0
    wave2.replicate=1
    wave2.func=exponential
    wave2.pars=[0.2]
    wave1.mult=wave2
    wave2.pars=[0.2]
    pval=(pot.read_u16())/4096
    freq=round(pval)+1
    setupwave(wavbuf[ibuf],freq,wave1); ibuf=(ibuf+1)%2   
    while expomode==True:
        if fsw.value()==1:
            expomode=False
            tonemode=True
        else:
            pval=(pot.read_u16())/4096
            nfreq=round(pval)+1
            if freq is not nfreq:
                freq=nfreq
                setupwave(wavbuf[ibuf],freq,wave1); ibuf=(ibuf+1)%2
#mode 4: 
if tonemode==True:
    blue.duty_u16(25025)
    red.duty_u16(25025)
    green.duty_u16(0)
    wave1=wave()
    wave1.amplitude=0.5
    wave1.offset=0.5
    wave1.phase=0.0
    wave1.replicate=4
    wave1.func=sine
    wave1.pars=[]
    pval=(pot.read_u16())/256
    freq=int(round(pval))+1
    setupwave(wavbuf[ibuf],freq,wave1); ibuf=(ibuf+1)%2
    while tonemode==True:
        if fsw.value()==1:
            tonemode=False
        else:
            pval=(pot.read_u16())/256
            nfreq=int(round(pval))+1
            if freq is not nfreq:
                freq=nfreq
                setupwave(wavbuf[ibuf],freq,wave1); ibuf=(ibuf+1)%2
#reset, future mode : noise
if tonemode==False:
    blue.duty_u16(10000)
    red.duty_u16(32025)
    green.duty_u16(32025)
    blue.freq(10)
    red.freq(20)
    green.freq(30)
    sleep(3)
    machine.reset()