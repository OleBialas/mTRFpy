# -*- coding: utf-8 -*-
"""
Created on Thu Jul 16 14:42:40 2020

@author: Jin Dou
"""
import sklearn as skl
import numpy as np
from sklearn.base import BaseEstimator,RegressorMixin, TransformerMixin
from sklearn.model_selection import ShuffleSplit,LeaveOneOut
from multiprocessing import Pool,shared_memory


from StellarInfra import IO as siIO
from . import DataStruct as ds
from . import Basics as bs
from . import Core
import sys

DirEnum = tuple([-1,1]) 

def funcTrainNVal(oInput):
    trainIdx = oInput[0]
    testIdx = oInput[1]
    idx = oInput[2]
    nSplits = oInput[3]
    modelParam = shared_memory.ShareableList(name='sharedModelParam') 
    Dir = modelParam[0]
    fs = modelParam[1]
    tmin_ms = modelParam[2]
    tmax_ms = modelParam[3]
    Lambda = modelParam[4]
    stim = modelParam[5]
    resp = modelParam[6]
    oTRF = CTRF()
    stimTrain = stim.selectByIndices(trainIdx)
    respTrain = resp.selectByIndices(trainIdx)
    oTRF.train(stimTrain, respTrain, Dir, fs, tmin_ms, tmax_ms, Lambda)
    
    stimTest = stim.selectByIndices(testIdx)
    respTest = resp.selectByIndices(testIdx)
    _,r,err = oTRF.predict(stimTest,respTest)
    sys.stdout.write("\r" + f"cross validation >>>>>..... split {idx}/{nSplits}\r")
    return (r,err)

def createSharedNArray(a,name):
    shm = shared_memory.SharedMemory(name=name,create=True, size=a.nbytes)
    b = np.ndarray(a.shape, dtype=a.dtype, buffer=shm.buf)
    b[:] = a[:]
    return b
    

def crossVal(stim:ds.CDataList,resp:ds.CDataList,
             Dir,fs,tmin_ms,tmax_ms,Lambda,
             random_state = 42,mode = None,nWorkers=1,n_Splits = 80, **kwargs):
    if mode == 'fast':
        nSplits = n_Splits
        testSize = 1/nSplits
        if testSize > 0.1:
            testSize = 0.1
        rs = ShuffleSplit(n_splits = nSplits,test_size=testSize,random_state=random_state)
    else:
        rs = LeaveOneOut()
        nStim = len(stim)
        nSplits = nStim
    
    if nWorkers <= 1:
        finalR = []
        finalErr = []
        idx = 0
        
        for trainIdx,testIdx in rs.split(stim):
            # print('def\rabc')
            # sys.stdout.write(f"cross validation >>>>>..... split {idx+1}/{nStim}")
            # sys.stdout.flush()
            print("\r" + f"cross validation >>>>>..... split {idx+1}/{nSplits}",end='\r')
            idx+=1
            oTRF = CTRF()
            stimTrain = stim.selectByIndices(trainIdx)
            respTrain = resp.selectByIndices(trainIdx)
            oTRF.train(stimTrain, respTrain, Dir, fs, tmin_ms, tmax_ms, Lambda, **kwargs)
            
            stimTest = stim.selectByIndices(testIdx)
            respTest = resp.selectByIndices(testIdx)
            _,r,err = oTRF.predict(stimTest,respTest)
            finalR.append(r)
            finalErr.append(err)
    else:
        splitParam = []
        idx=1
        for trainIdx,testIdx in rs.split(stim):
            splitParam.append([trainIdx,testIdx,idx,nSplits])
            idx+=1
            
        modelParam = shared_memory.ShareableList(
            [Dir,fs, tmin_ms, tmax_ms, Lambda],
            name= 'sharedModelParam')
        
        sharedStim = createSharedNArray(stim, 'sharedStim')
        sharedResp = createSharedNArray(resp, 'sharedResp')
        
        # stop
        with Pool(nWorkers) as pool:
            out = pool.imap(funcTrainNVal, splitParam,chunksize=int(nSplits/nWorkers))
            finalR = [i[0] for i in out]
            finalErr = [i[1] for i in out]
    finalR = np.concatenate(finalR)
    finalErr = np.concatenate(finalErr)
    return finalR,finalErr#np.mean(finalR,axis=0),np.mean(finalErr,axis=0)

class CTRF:
    
    def __init__(self,):
        self.w = None
        self.b = None
        self.t = None
        self.Dir = None
        self.Type = 'multi'
        self.Zeropad = True
        self.fs = -1
        self._oCuda = None
        
    def train(self,stim,resp,Dir,fs,tmin_ms,tmax_ms,Lambda,**kwargs):
        assert Dir in DirEnum
        
        if (Dir == 1):
            x = stim
            y = resp
        else:
            x = resp
            y = stim
            tmin_ms, tmax_ms = Dir * tmax_ms, Dir * tmin_ms
        
        w,b,lags = bs.train(x,y,fs,tmin_ms,tmax_ms,Lambda,oCuda = self._oCuda,**kwargs)
        
        if kwargs.get('Type') != None:
            self.type = kwargs.get('Type')
        
        if kwargs.get('Zeropad') != None:
            self.Zeropad = kwargs.get('Zeropad')
            
        self.w, self.b = w, b
        self.Dir = Dir
        self.t = Core.Idxs2msec(lags,fs)
        self.fs = fs
    
    
    def predict(self,stim,resp = None,**kwargs):
        assert self.Dir in DirEnum
        if self.Dir == 1:
            x = stim; y = resp
        else:
            x = resp; y = stim
        
        return bs.predict(self,x,y,zeropad = self.Zeropad,**kwargs)
    
    def save(self,path,name):
        output = dict()
        for i in self.__dict__:
            output[i] = self.__dict__[i]
        
        siIO.saveObject(output, path,name, '.mtrf')
        
    def load(self,path):
        temp = siIO.loadObject(path)
        for i in temp:
            setattr(self, i, temp[i])
            
    def cuda(self,debug = False):
        from .CudaCore import CCoreCuda
        oCuda = CCoreCuda()
        Core.oCuda = oCuda
        ds.oCuda = oCuda
        self._oCuda = oCuda
        self._oCuda.DEBUG = debug
        
    def cpu(self):
        Core.oCuda = None
        ds.oCuda = None
        self._oCuda = None
        
    def plotWeights(self,vecNames = None,ylim = None):

        '''desined for models trained with combined vector '''
        from matplotlib import pyplot as plt
        times = self.t
        out = list()
        for i in range(self.w.shape[0]):
            weights = self.w[i,:,:]#take mean along the input dimension
            fig1 = plt.figure()
            plt.plot(times,weights[:,:])
            plt.title(vecNames[i])
            plt.xlabel("time (ms)")
            plt.ylabel("a.u.")
            if ylim:
                plt.ylim(ylim)
            out.append(fig1)
        return out
        

class CSKlearnTRF(BaseEstimator,RegressorMixin, TransformerMixin, CTRF):
    '''
    main difference is that Dir will always be 1
    
    '''
    
    def __init__(self,fs, tmin_ms, tmax_ms, Lambda,**kwargs):
        super().__init__()
        self.Dir = 1
        self.fs = fs
        self.tmin_ms = tmin_ms
        self.tmax_ms = tmax_ms
        self.Lambda = Lambda
        self.Type = 'multi'
        self.Zeropad = True
        self.kwargs = kwargs
        
    def fit(self,x,y):
        x = skl.utils.check_array(x)
        y = skl.utils.check_array(y)
        self.train(x,y,self.Dir,self.fs,self.tmin_ms,self.tmax_ms,self.Lambda,**self.kwargs)
    
    def predict(self,x):
        pass
    
    def transform(self,x):
        pass