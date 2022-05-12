# -*- coding: utf-8 -*-
"""
Created on Sat May  7 00:01:54 2022

@author: Jin Dou
"""

'''
replicating the example provided in mTRFToolbox:
    https://github.com/mickcrosse/mTRF-Toolbox
    
'''

from StellarInfra import siIO
from StellarInfra import StageControl
from mTRFpy.Model import CTRF
from mTRFpy.Tools import cmp2NArray

oStage = StageControl.CStageControl([2,3])

if oStage(1):
    #simple encoder validation
    speechAndRespData = siIO.loadMatFile('speech_data.mat')
    encoderResult = siIO.loadMatFile('EncoderTask.mat')
    stim = speechAndRespData['stim']
    resp = speechAndRespData['resp']
    fs = speechAndRespData['fs'][0,0]
    oTRFEncoder = CTRF()
    oTRFEncoder.train(stim,resp,1,fs,-100,200,100)
    assert cmp2NArray(oTRFEncoder.w,encoderResult['modelEncoder']['w'][0,0],10)
    assert cmp2NArray(oTRFEncoder.b,encoderResult['modelEncoder']['b'][0,0],12)
    predE,rE,errE = oTRFEncoder.predict(stim,resp)
    assert cmp2NArray(predE[0], encoderResult['predResp'],10)
    assert cmp2NArray(rE, encoderResult['predRespStats']['r'][0,0],11)
    assert cmp2NArray(errE, encoderResult['predRespStats']['err'][0,0],13)

if oStage(2):
    #simple decoder validation
    speechAndRespData = siIO.loadMatFile('speech_data.mat')
    decoderResult = siIO.loadMatFile('DecoderTask.mat')
    stim = speechAndRespData['stim']
    resp = speechAndRespData['resp']
    fs = speechAndRespData['fs'][0,0]
    oTRFDecoder = CTRF()
    oTRFDecoder.train(stim,resp,-1,fs,-100,200,100)
    assert cmp2NArray(oTRFDecoder.w,decoderResult['modelDecoder']['w'][0,0],8)
    assert cmp2NArray(oTRFDecoder.b,decoderResult['modelDecoder']['b'][0,0],11)
    predD,rD,errD = oTRFDecoder.predict(stim,resp)
    assert cmp2NArray(predD[0], decoderResult['predStim'],8)
    assert cmp2NArray(rD, decoderResult['predStimStats']['r'][0,0],12)
    assert cmp2NArray(errD, decoderResult['predStimStats']['err'][0,0],16)
