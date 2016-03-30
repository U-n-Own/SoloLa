#!/usr/bin/env python
# encoding: utf-8
"""
Author: Yuan-Ping Chen
Data: 2016/03/10
----------------------------------------------------------------------
Expression style recognition: automatically recognize the electric 
                              guitar expression style.
----------------------------------------------------------------------
Args:
    input_files:    Audio files to be processed. 
                    Only the wav files would be considered.



    output_dir:     Directory for storing the results.

Optional args:
    Please refer to --help.
----------------------------------------------------------------------
Returns:
    expression_style_note:  Text file of array, storing the onset, offset 
                            and pitch of each note as well as its expression.
                            The file is attached with .expression_style_note
                             extenion.

                            Example:
                              Pit   On    Dur   B     P     H     S     V    
                            [ 66    1.24  0.5   2     0     0            ]

                            Pi:     pitch (MIDI number)
                            On:     onset (sec.)
                            Dur:    duration (sec.)
                            B:      string bend (0 for none,
                                                 1 for bend by 1 semitone,
                                                 2 for bend by 2 semitone,
                                                 3 for bend by 3 semitone)
                            P:      pull-off (0 for none, 
                                              1 for employed)
                            H:      hammer-on (0 for none, 
                                               1 for employed)
                            S:      slide (0 for none, 
                                           1 for long slide in the begining, 
                                           2 for long slide in the end)
                            V:      vibrato (0 for none,
                                             1 for vibrato with entext of 1 semitone,
                                             2 for vibrato with entext of 2 semitone)
                                             
"""

import glob, os
import numpy as np
from scipy.io import wavfile
import math
import subprocess as subp
import operator
import pickle
from essentia import *
from essentia.standard import *
from Candidate_selection import continuously_ascending_descending_pattern, candidate_selection
from Feature_extraction import feature_extractor
from GuitarTranscription_parameters import *

class Common(object):
    @staticmethod
    def update(expression_style_note, note_with_expression_style, technique, sub_technique):
        """
        Update expression_style_note array.

        :param expression_style_note:       numpy array of expression_style_note.
        :param note_with_expression_style:  numpy array of note event with expression style.
        :param technique:                   string of technique.
        :param sub_technique:               float number of sub technique.
        :returns:                           numpy array of updated expression_style_note.
        """
        if technique=='bend': t = 3
        elif technique=='pull': t = 4
        elif technique=='hamm': t = 5
        elif technique=='slide': t = 6
        elif technique=='vibrato': t = 7
        note_to_be_deleted = np.empty([0])
        for r_n in range(len(note_with_expression_style)):
            for r_esn in range(len(expression_style_note)):
                # if the onsets of expression_style_note and note_with_expression_style are equal
                if note_with_expression_style[r_n,1]==expression_style_note[r_esn,1]:   
                    # if the duration of current expression_style_note is larger than or equal to the duration of note_with_expression_style 
                    if expression_style_note[r_esn,2]>=note_with_expression_style[r_n,2]:
                        expression_style_note[r_esn,2]=note_with_expression_style[r_n,2]
                        expression_style_note[r_esn,t]=sub_technique
                    else:
                        # loop from the next expression_style_note
                        for r_esn_r in range(r_esn+1,len(expression_style_note)):
                            expression_style_note_offset = expression_style_note[r_esn_r,1]+expression_style_note[r_esn_r,2]
                            note_with_expression_style_offset = note_with_expression_style[r_n,1]+note_with_expression_style[r_n,2]
                            # check if the offset of expression_style_note  is larger than or equal to the offset of note_with_expression_style
                            if expression_style_note_offset>=note_with_expression_style_offset:
                                # the expression_style_note will not be deleted if the onset exceed the offset of note_with_expression_style, vice versa
                                if expression_style_note[r_esn_r,1]>note_with_expression_style_offset:
                                    expression_style_note[r_esn,2]=note_with_expression_style[r_n,2]
                                    expression_style_note[r_esn,t]=sub_technique
                                    break
                                else:
                                    expression_style_note[r_esn,2]=note_with_expression_style[r_n,2]
                                    expression_style_note[r_esn,t]=sub_technique
                                    note_to_be_deleted = np.append(note_to_be_deleted,[r_esn_r], axis=0)
                                    break
                            else:
                                note_to_be_deleted = np.append(note_to_be_deleted,[r_esn_r], axis=0)

        expression_style_note = np.delete(expression_style_note, note_to_be_deleted,axis=0)
        return expression_style_note

    def sec_2_note(self):
        self.long_slide = np.empty([0,3])
        for r_lss in range(len(self.long_slide_sec)):
            for r_mn in range(len(self.merged_note)):
                if self.long_slide_sec[r_lss,0]>self.merged_note[r_mn,1] and self.long_slide_sec[r_lss,0]<self.merged_note[r_mn,1]+self.merged_note[r_mn,2]:
                    long_slide_pitch = self.merged_note[r_mn,0]
                    long_slide_onset = self.merged_note[r_mn,1]
                    if r_mn+1<=len(self.merged_note):
                        for r_mn_r in range(r_mn+1,len(self.merged_note)):
                            if self.long_slide_sec[r_lss,1]>self.merged_note[r_mn_r,1] and self.long_slide_sec[r_lss,1]<self.merged_note[r_mn_r,1]+self.merged_note[r_mn_r,2]:
                                long_slide_offset = self.merged_note[r_mn_r,1]+self.merged_note[r_mn_r,2]
                            else:
                                long_slide_offset = self.long_slide_sec[r_lss,1]
                    else:
                        long_slide_offset = self.long_slide_sec[r_lss,1]
                    long_slide = [long_slide_pitch, long_slide_onset, long_slide_offset]
                    self.long_slide = np.append(self.long_slide, [long_slide], axis=0)  

class WideVibrato(Common):

    def __init__(self, pruned_note):
        """
        Creates a new Wav object instance of the given file.

        :param filename: name of the .wav file

        """
        # self.merged_note = merged_note.copy()
        self.technique = 'vibrato'
        self.pruned_note = pruned_note

    def detect(self):
        merged_notes, self.super_wide_vibrato = self.merge_wide_vibrato(self.pruned_note,2)
        # vibrato with extent of 1 semitone
        merged_notes, self.wide_vibrato = self.merge_wide_vibrato(merged_notes,1)


        # event = np.zeros((merged_notes.shape[0],5))
        expression_style_note = np.hstack((merged_notes,np.zeros((merged_notes.shape[0],5))))

        expression_style_note = Common.update(expression_style_note=expression_style_note, 
                                              note_with_expression_style=self.super_wide_vibrato, 
                                              technique=self.technique, 
                                              sub_technique=2)

        expression_style_note = Common.update(expression_style_note=expression_style_note, 
                                              note_with_expression_style=self.wide_vibrato, 
                                              technique=self.technique, 
                                              sub_technique=1)
        return expression_style_note

    @staticmethod
    def merge_wide_vibrato(note_pseudo,extent):
        """
        Merge notes of wide vibrato by merging series of notes in serrated patter 
        Usage:
        :param note:     array of notes [pitch(MIDI#) onset(sec) duration(sec)].
        :param extent:   the heigh in semitone of the serrated pattern.
        :returns:        merged notes.
                         wide vibrato notes.         

        """
        note = note_pseudo.copy()
        wide_vibrato = np.empty([0,3])
        merged_notes = np.empty([0,3])
        for n in range(note.shape[0]):
            # the pitch difference of current note and next note is a semitone:
            if note[n,0]!=0 and n+1<=note.shape[0]-1:
                if note[n+1,0]-note[n,0]==extent and note[n+1,1]-(note[n,1]+note[n,2])<0.01:
                    pitch = note[n,0]
                    pitch_next = note[n+1,0]
                    onset_note = n
                    offset_note = n+1
                    sign = np.sign(pitch_next-pitch)
                    if offset_note+1<=note.shape[0]-1:
                        while( abs(note[offset_note+1,0]-note[offset_note,0])==extent and \
                            np.sign(note[offset_note+1,0]-note[offset_note,0]) != sign and \
                            note[offset_note+1,1]-(note[offset_note,1]+note[offset_note,2])<0.01 and \
                            offset_note+1<note.shape[0]-1):
                            sign = np.sign(note[offset_note+1,0]-note[offset_note,0])
                            if offset_note+1<note.shape[0]-1:
                                offset_note = offset_note+1
                            else:
                                break
                    num_notes = offset_note-onset_note+1
                    if num_notes>=5:                
                        onset_time = note[onset_note,1]
                        duration = note[offset_note,1]+note[offset_note,2]-onset_time
                        merged_notes = np.append(merged_notes,[[pitch, onset_time, duration]],axis=0)
                        wide_vibrato = np.append(wide_vibrato,[[pitch, onset_time, duration]],axis=0)
                    else:
                        merged_notes = np.append(merged_notes,note[onset_note:offset_note+1,:],axis=0)
                    note[onset_note:offset_note+1,0] = 0
                else:
                    merged_notes = np.append(merged_notes,[note[n,:]],axis=0)
            elif note[n,0]!=0 and n+1>note.shape[0]-1:
                merged_notes = np.append(merged_notes,[note[-1,:]],axis=0)
        # append last note 
        return merged_notes, wide_vibrato

class LongSlide(Common):

    def __init__(self, melody, hop=256, sr=44100, max_transition_note_duration=0.09, min_transition_note_duration=0.015):
        """
        Creates a new Wav object instance of the given file.

        :param filename: name of the .wav file

        """
        self.melody = melody
        self.technique = 'slide'
        self.hop = hop
        self.sr = sr
        self.max_transition_note_duration = max_transition_note_duration
        self.min_transition_note_duration = min_transition_note_duration
        self.long_slide_sec = np.empty([0,2])
        self.quantised_melody = self.quantize(self.melody)
        
    @staticmethod
    def quantize(data, partitions=range(0, 90, 1), codebook=range(0, 91, 1)):
        """
        Quantise array into given scale.

        Usage:
          index, quants = quantize([3, 34, 84, 40, 23], range(10, 90, 10), range(10, 100, 10))
          >>> index
          [0, 3, 8, 3, 2]
          >>> quants
          [10, 40, 90, 40, 30]
          
        """
        indices = []
        quantised_data = []
        halfstep = float(partitions[1]-partitions[0])/2
        for datum in data:
            index = 0
            while index < len(partitions) and datum >= partitions[index]-halfstep:
                index += 1
            indices.append(index-1)
            quantised_data.append(codebook[index-1])
        indices = np.asarray(indices)
        quantised_data = np.asarray(quantised_data)
        quantised_data[np.nonzero(quantised_data<0)[0]] = 0
        
        return quantised_data

    @staticmethod
    def frame2note(quantised_melody,hop,sr):
        """
        Convert pitch sequence into note[onset pitch duration]
        :param quantised_melody: quantised pitch sequence.
        :param hop:              the hop size of pitch contour.
        :param sr:               the sampling rate of pitch contour.
        :returns:                note [onset pitch duration]
        """
        note = np.empty([0,3])
        frame = quantised_melody.copy()
        for f in range(frame.shape[0]-1):
            # The frame is not polyphonic and the frame is voiced 
            if frame[f]!=0:
                pitch = frame[f]
                onset = f
                offset = f
                while(frame[offset+1]==frame[offset] and offset+1<frame.shape[0]):
                    offset = offset+1
                duration = offset-onset+1
                note = np.append(note,[[pitch,onset,duration]],axis=0)
                frame[onset:offset+1] = 0
        note[:,1] = note[:,1]*hop/sr
        note[:,2] = note[:,2]*hop/sr
        return note

    def detect(self, expression_style_note):
        """
        Find long stair pattern(distance greater than three semitones) in quantised pitch sequence.
        :param pitch_contour:                quantised pitch sequence.
        :param hop:                          the step size of melody contour.
        :param sr:                           the sampling rate of melody contour.
        :param max_transition_note_duration: the maximal lenght of the note in middle of the ladder.
        :param min_transition_note_duration: the minimal lenght of the note in middle of the ladder.

        """
        # find downward-long-stairs
        # convert frame-level pitch contour into notes
        note = self.frame2note(self.quantised_melody,self.hop,self.sr)
        for n in range(note.shape[0]-1):
            if note[n,0]!=0:
                pitch = note[n,0]
                onset_note = n
                offset_note = n
                # trace the ladder pattern
                while(note[offset_note+1,0]+1==note[offset_note,0] and \
                    note[offset_note+1,2]>=self.min_transition_note_duration and \
                    note[offset_note+1,2]<=self.max_transition_note_duration and \
                    offset_note+2<note.shape[0]):
                    offset_note = offset_note+1
                step = offset_note-onset_note+1
                # recognized as long slide if the step number of ladder is larger than 5
                if step>=5:
                    onset_time = note[onset_note,1]
                    offset_time = note[offset_note,1]+note[offset_note,2]
                    self.long_slide_sec = np.append(self.long_slide_sec,[[onset_time,offset_time]],axis=0)
                note[onset_note:offset_note+1,0] = 0

        # convert time segment of slide out into note event
        self.long_slide = self.long_slide_sec_2_long_slide(self.long_slide_sec, expression_style_note[:,0:3])
        # update expression_style_note array
        expression_style_note = Common.update(expression_style_note=expression_style_note, 
                                              note_with_expression_style=self.long_slide, 
                                              technique=self.technique, 
                                              sub_technique=2)
        return expression_style_note

    @staticmethod
    def long_slide_sec_2_long_slide(long_slide_sec, note):
        long_slide = np.empty([0,3])
        for r_lss in range(len(long_slide_sec)):
            for r_mn in range(len(note)):
                if long_slide_sec[r_lss,0]>note[r_mn,1] and long_slide_sec[r_lss,0]<note[r_mn,1]+note[r_mn,2]:
                    long_slide_pitch = note[r_mn,0]
                    long_slide_onset = note[r_mn,1]
                    if r_mn+1<=len(note):
                        # loop from the next note
                        for r_mn_r in range(r_mn+1,len(note)):
                            if note[r_mn_r,1]+note[r_mn_r,2]>=long_slide_sec[r_lss,1]:
                                if note[r_mn_r,1]>long_slide_sec[r_lss,1]:
                                    long_slide_offset = long_slide_sec[r_lss,1]
                                    long_slide_dur = long_slide_offset-long_slide_onset
                                    break
                                else:
                                    long_slide_offset = note[r_mn_r,1]+note[r_mn_r,2]
                                    long_slide_dur = long_slide_offset-long_slide_onset
                                    break
                    else:
                        long_slide_offset = long_slide_sec[r_lss,1]
                        long_slide_dur = long_slide_offset-long_slide_onset
                    long_slide_note = [long_slide_pitch, long_slide_onset, long_slide_dur]
                    long_slide = np.append(long_slide, [long_slide_note], axis=0)
        return long_slide

    def evaluate(self,answer_path):
        if type(answer_path).__name__=='ndarray':
            answer = answer_path.copy()
        else:
            answer = np.loadtxt(answer_path)
        numTP = 0.
        TP = np.array([])
        FP = np.array([])
        FN = np.array([])
        estimation = self.long_slide_sec.copy()
        estimation_mask = np.ones(len(self.long_slide_sec))
        answer_mask = np.ones(len(answer))
        for e in range(len(estimation)):
            for a in range(len(answer)):    
                if answer[a,0]>=estimation[e,0] and answer[a,0]<=estimation[e,1]:
                    answer_mask[a] = 0
                    estimation_mask[e] = 0
                    numTP = numTP+1
        numFN = np.sum(answer_mask)
        numFP = np.sum(estimation_mask)
        TP = estimation[np.nonzero(estimation_mask==0)[0]]
        FP = estimation[np.nonzero(estimation_mask==1)[0]]
        FN = answer[np.nonzero(answer_mask==1)[0]]
        P = numTP/(numTP+numFP)
        R = numTP/(numTP+numFN)
        F = 2*P*R/(P+R)
        return P, R, F, TP, FP, FN, numTP, numFP, numFN



def long_CAD_pattern_detection(note, CAD_pattern):
    # need to modify to detection four notes covered with pattern.
    """
    Candidate selection for bend and slide by rules.
    All the candidates must meet: 
        i) continuously ascending or descending pattern covers three note.
        ii) The pitch difference of the three covered notes is a semitone

    :param      note:               2-D ndarray[pitch(MIDI). onset(s). duration(s)] 
                                    notes after mergin vibrato.

    :param      CAD_pattern:        1-D ndarray[onset(s). offset(s).]                
                                    continuously ascending or descending pattern.

    :returns    CAD_pattern:        1-D ndarray[onset(s). offset(s).]                
                                    continuously ascending or descending pattern.

    :returns    note_of_long_CAD:   1-D ndarray[onset(s). offset(s).]                
                                    continuously ascending or descending pattern.
    """
    note_of_long_CAD = np.empty([0,3])
    long_CAD_index = []
    note_of_long_CAD_index = []
    pseudo_CAD = CAD_pattern.copy()
    pseudo_note = note.copy()
    # Loop in each pattern
    for p in range(pseudo_CAD.shape[0]):
        onset_pattern = pseudo_CAD[p,0]
        offset_pattern = pseudo_CAD[p,1]
        # Loop in each note
        for n in range(pseudo_note.shape[0]):
            onset_note = pseudo_note[n,1]
            offset_note = pseudo_note[n,1]+pseudo_note[n,2]
            # Find notes where pattern located
            if onset_pattern >= onset_note and onset_pattern <= offset_note:
                if n+3>=pseudo_note.shape[0]:
                    break
                for m in range(n+2,n+4):
                    onset_note = pseudo_note[m,1]
                    offset_note = pseudo_note[m,1]+pseudo_note[m,2]
                    if offset_pattern >= onset_note and offset_pattern <= offset_note:
                        if m-n>=2 and m-n<=3 and abs(pseudo_note[n,0]-pseudo_note[m,0])<=3:
                            pitch = pseudo_note[n,0]
                            onset = pseudo_note[n,1]
                            duration = pseudo_note[n,2]+pseudo_note[n+1,2]+pseudo_note[n+2,2]
                            note_of_long_CAD = np.append(note_of_long_CAD,[[pitch, onset, duration]],axis = 0)
                            long_CAD_index.append(p)
                            note_of_long_CAD_index.append(n)
                            note_of_long_CAD_index.append(n+1)
                            note_of_long_CAD_index.append(n+2)
    long_CAD = pseudo_CAD[long_CAD_index,:]
    short_CAD = np.delete(pseudo_CAD,long_CAD_index,axis=0)
    note_of_short_CAD = np.delete(pseudo_note,note_of_long_CAD_index,axis=0)
    return note_of_long_CAD, note_of_short_CAD, long_CAD, short_CAD


def long_pattern_evaluate(pattern,bend_answer_path,slide_answer_path):
    if type(bend_answer_path).__name__=='ndarray':
        bend_answer = bend_answer_path.copy()
    else:
        bend_answer = np.loadtxt(bend_answer_path)
    if type(slide_answer_path).__name__=='ndarray':
        slide_answer = slide_answer_path.copy()
    else:
        slide_answer = np.loadtxt(slide_answer_path)    
    TP_bend = np.array([]);TP_slide = np.array([])
    FN_bend = np.array([]);FN_slide = np.array([])
    candidate = pattern.copy()
    candidate_mask = np.ones(len(candidate))
    bend_answer_mask = np.ones(len(bend_answer))
    slide_answer_mask = np.ones(len(slide_answer))  
    for c in range(len(candidate)):
        for b in range(len(bend_answer)):
            if bend_answer[b,0]>candidate[c,0] and bend_answer[b,0]<candidate[c,1]:
                candidate_mask[c] = 0
                bend_answer_mask[b] = 0
        for s in range(len(slide_answer)):
            if slide_answer[s,0]>candidate[c,0] and slide_answer[s,0]<candidate[c,1]:
                candidate_mask[c] = 0
                slide_answer_mask[s] = 0

    num_invalid_candidate = np.sum(candidate_mask)
    num_valid_candidate = len(candidate_mask)-num_invalid_candidate
    invalid_candidate = np.delete(candidate,np.nonzero(candidate_mask==0)[0],axis = 0)

    TP_bend = bend_answer[np.nonzero(bend_answer_mask==0)[0]]
    FN_bend = bend_answer[np.nonzero(bend_answer_mask==1)[0]]
    TP_slide = slide_answer[np.nonzero(slide_answer_mask==0)[0]]
    FN_slide = slide_answer[np.nonzero(slide_answer_mask==1)[0]]
    
    return num_valid_candidate, num_invalid_candidate, invalid_candidate, TP_bend, TP_slide, FN_bend, FN_slide


def short_pattern_evaluate(pattern,bend_answer_path,slide_answer_path,pullhamm_answer_path):
    if type(bend_answer_path).__name__=='ndarray':
        bend_answer = bend_answer_path.copy()
    else:
        bend_answer = np.loadtxt(bend_answer_path)
    if type(slide_answer_path).__name__=='ndarray':
        slide_answer = slide_answer_path.copy()
    else:
        slide_answer = np.loadtxt(slide_answer_path)
    if type(pullhamm_answer_path).__name__=='ndarray':
        pullhamm_answer = pullhamm_answer_path.copy()
    else:
        pullhamm_answer = np.loadtxt(pullhamm_answer_path)
    candidate = pattern.copy()
    candidate_mask = np.ones(len(candidate))
    bend_answer_mask = np.ones(len(bend_answer))
    slide_answer_mask = np.ones(len(slide_answer))
    pullhamm_answer_mask = np.ones(len(pullhamm_answer))
    for c in range(len(candidate)):
        for b in range(len(bend_answer)):
            if bend_answer[b,0]>candidate[c,0] and bend_answer[b,0]<candidate[c,1]:
                candidate_mask[c] = 0
                bend_answer_mask[b] = 0
        for s in range(len(slide_answer)):
            if slide_answer[s,0]>candidate[c,0] and slide_answer[s,0]<candidate[c,1]:
                candidate_mask[c] = 0
                slide_answer_mask[s] = 0
        for p in range(len(pullhamm_answer)):
            if pullhamm_answer[p,0]>candidate[c,0] and pullhamm_answer[p,0]<candidate[c,1]:
                candidate_mask[c] = 0
                pullhamm_answer_mask[p] = 0

    numInvalidCandidate = np.sum(candidate_mask)
    numValidCandidate = len(candidate_mask)-numInvalidCandidate
    InvalidCandidate = np.delete(candidate,np.nonzero(candidate_mask==0)[0],axis = 0)

    TP_bend = bend_answer[np.nonzero(bend_answer_mask==0)[0]]
    FN_bend = bend_answer[np.nonzero(bend_answer_mask==1)[0]]
    TP_slide = slide_answer[np.nonzero(slide_answer_mask==0)[0]]
    FN_slide = slide_answer[np.nonzero(slide_answer_mask==1)[0]]
    TP_pullhamm = pullhamm_answer[np.nonzero(pullhamm_answer_mask==0)[0]]
    FN_pullhamm = pullhamm_answer[np.nonzero(pullhamm_answer_mask==1)[0]]

    return numValidCandidate, numInvalidCandidate, InvalidCandidate, TP_bend, TP_slide, TP_pullhamm, FN_bend, FN_slide, FN_pullhamm


def transition_locater(note,step,direction = None,min_note_duration = 0.05,gap_tolerence = 0.05):
    """
    Find the timestamp of transition of two consecutive notes.
    Usage:
    :param note:              array of notes [pitch(hertz) onset(sec) duration(sec)].
    :param step:              the pithc distance between two notes.
    :param min_note_duration: the minimal duration of two consecutive notes
    :param gap_tolerence:     the minimal silent gap between two notes

    """
    transition = []
    for n in range(note.shape[0]-1):
        # print 'abs(np.log(note[n,0])-np.log(note[n+1,0])) is ', abs(np.log(note[n,0])-np.log(note[n+1,0]))
        # print 'note[n,2] is ', note[n,2]
        # print 'note[n+1,2] is ', note[n+1,2]
        # print 'min_note_duration*fs/hop is ', min_note_duration*fs/hop
        # print abs(np.log(note[n,0])-np.log(note[n+1,0]))
        # print '(note[n+1,1]-(note[n,1]+note[n,2])) is ', (note[n+1,1]-(note[n,1]+note[n,2]))
        # print 'gap_tolerence*fs/hop is ', gap_tolerence*fs/hop
                                # the pitch difference of two consecutive notes must smaller than or equal to given step
        is_transition_candi =   (abs(np.log(note[n,0])-np.log(note[n+1,0])) < step*0.0578+0.0578/2 and \
                                # the pitch difference of two consecutive notes must larger than or equal to given step
                                abs(np.log(note[n,0])-np.log(note[n+1,0])) > step*0.0578-0.0578/2 and \
                                # the duration of first note must longer than threshold
                                note[n,2]>min_note_duration and \
                                # the duration of second note must longer than threshold
                                note[n+1,2]>min_note_duration and \
                                # the gap between two consecutive notes must smaller than threshold
                                (note[n+1,1]-(note[n,1]+note[n,2])) < gap_tolerence)
        if is_transition_candi:
            if direction == None:
                transition.append(np.mean([note[n,1]+note[n,2], note[n+1,1]]))
            elif direction == 'upward':
                if note[n,0]<note[n+1,0]:
                    transition.append(np.mean([note[n,1]+note[n,2], note[n+1,1]]))
            elif direction == 'downward':
                if note[n,0]>note[n+1,0]:
                    transition.append(np.mean([note[n,1]+note[n,2], note[n+1,1]]))


    transition = np.asarray(transition)
    return transition


def parse_input_files(input_files, ext):
    """
    Collect all files by given extension.

    :param input_files:  list of input files or directories.
    :param ext:          the string of file extension.
    :returns:            a list of stings of file name.

    """
    from os.path import basename, isdir
    import fnmatch
    import glob
    files = []

    # check what we have (file/path)
    if isdir(input_files):
        # use all files with .raw.melody in the given path
        files = fnmatch.filter(glob.glob(input_files+'/*'), '*'+ext)
    else:
        # file was given, append to list
        if basename(input_files).find(ext)!=-1:
            files.append(input_files)
    print '  Input files: '
    for f in files: print '    ', f
    return files

def parser():
    """
    Parses the command line arguments.

    :param lgd:       use local group delay weighting by default
    :param threshold: default value for threshold

    """
    import argparse
    # define parser
    p = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description="""
    If invoked without any parameters, the software S1 Extract melody contour,
     track notes and timestmaps of intersection of ad continuous pitch sequence
     inthe given files, the pipeline is as follows,

        S1.1 Extract melody contour
        S1.2 Note tracking
        S1.3 Find continuously ascending/descending (CAD) F0 sequence patterns
        S1.4 Find intersection of note and pattern 
             (Candidate selection of {bend,slide,pull-off,hammer-on,normal})
    """)
    # general options
    p.add_argument('input_audios', type=str, metavar='input_audios',
                   help='audio files to be processed')
    p.add_argument('input_melody', type=str, metavar='input_melody',
                   help='melody contours to be processed')
    p.add_argument('input_note', type=str, metavar='input_note',
                   help='note events to be processed')
    p.add_argument('input_model', type=str, metavar='input_model',
                   help='pre-trained classifier')
    p.add_argument('output_dir', type=str, metavar='output_dir',
                   help='output directory.')
    # version
    p.add_argument('--version', action='version',
                   version='%(prog)spec 1.03 (2016-03-20)')
    # parse arguments
    args = p.parse_args()

    # return args
    return args


def main(args):
    print 'Running expression style recognition...'
    # parse and list files to be processed
    audio_files = parse_input_files(args.input_audios, ext='.wav')
    
    # create result directory
    if not os.path.exists(args.output_dir): os.makedirs(args.output_dir)
    print '  Output directory: ', '\n', '    ', args.output_dir

    for f in audio_files:
        ext = os.path.basename(f).split('.')[-1]
        name = os.path.basename(f).split('.')[0]      
        # load melody 
        melody_path = args.input_melody+os.sep+name+'.MIDI.smooth.melody'
        try:
            MIDI_smooth_melody = np.loadtxt(melody_path)
        except IOError:
            print 'The melody contour of ', name, ' doesn\'t exist!'

        # load note
        note_path = args.input_note+os.sep+name+'.pruned.note'
        try:
            pruned_note = np.loadtxt(note_path)
        except IOError:
            print 'The note event of ', name, ' doesn\'t exist!'     

        """
        ------------------------------------------------------------------------------------------
        S1. Recognize expression styles by heuristics
        ------------------------------------------------------------------------------------------
        """
        """
        S1.1 Detect wide vibrato by recognizing the serrated pattern in note events
        """
        WV = WideVibrato(pruned_note)
        expression_style_note = WV.detect()
        # save expression_style_note
        np.savetxt(args.output_dir+os.sep+name+'.after_WideVibrato.expression_style_note',expression_style_note, fmt='%s')

        """
        S1.1 Detect slide in/out by recognizing the ladder pattern in quantised melody contour
        """
        LS = LongSlide(MIDI_smooth_melody, hop=contour_hop, sr=contour_sr, 
                       max_transition_note_duration=max_transition_note_duration, 
                       min_transition_note_duration=min_transition_note_duration)
        expression_style_note = LS.detect(expression_style_note)        
        # save expression_style_note
        np.savetxt(args.output_dir+os.sep+name+'.after_LongSlide.expression_style_note',expression_style_note, fmt='%s')

        """
        ------------------------------------------------------------------------------------------
        S2. Recognize expression styles by Support Vector Machine
        ------------------------------------------------------------------------------------------
        """
        """
        S2.1 Find continuously ascending or descending pattern in melody contour.
        """
        # find continuously ascending (CAD) F0 sequence patterns
        ascending_pattern, ascending_pitch_contour = continuously_ascending_descending_pattern(
                                MIDI_smooth_melody,direction='up',MinLastingDuration=0.05, 
                                MaxPitchDifference=3.8, MinPitchDifference=0.8,hop=contour_hop,sr=contour_sr)
        # find continuously descending (CAD) F0 sequence patterns
        descending_pattern, descending_pitch_contour = continuously_ascending_descending_pattern(
                                MIDI_smooth_melody,direction='down',MinLastingDuration=0.05, 
                                MaxPitchDifference=3.8, MinPitchDifference=0.8,hop=contour_hop,sr=contour_sr)
        # save result: CAD F0 sequence pattern
        np.savetxt(args.output_dir+os.sep+name+'.ascending.pattern',ascending_pattern, fmt='%s')
        np.savetxt(args.output_dir+os.sep+name+'.ascending.pitch_contour',ascending_pitch_contour, fmt='%s')
        np.savetxt(args.output_dir+os.sep+name+'.descending.pattern',descending_pattern, fmt='%s')
        np.savetxt(args.output_dir+os.sep+name+'.descending.pitch_contour',descending_pitch_contour, fmt='%s')

        """
        S2.2 Detect slow bend by searching consecutive adjacent three or four notes whichc are cover by CAD pattern.

        """
        long_ascending_note, note_short_ascending, long_ascending_pattern, short_ascending_pattern = long_CAD_pattern_detection(expression_style_note[:,0:3], ascending_pattern)
        # num_valid_candidate, num_invalid_candidate, invalid_candidate, TP_bend, TP_slide, FN_bend, FN_slide = long_pattern_evaluate(long_ascending_pattern,join(bend_answer_dir,name_ext),FN_slide)       
        long_descending_note, note_short_descending, long_descending_pattern, short_descending_pattern = long_CAD_pattern_detection(expression_style_note[:,0:3], descending_pattern)
        # num_valid_candidate, num_invalid_candidate, invalid_candidate, TP_release, TP_slide, FN_release, FN_slide = long_pattern_evaluate(long_descending_pattern,join(release_answer_dir,name_ext),FN_slide)     
        np.savetxt(args.output_dir+os.sep+name+'.long.ascending.note', long_ascending_note, fmt='%s')
        np.savetxt(args.output_dir+os.sep+name+'.long.descending.note', long_descending_note, fmt='%s')

        """
        S2.3 Candidate selection by finding intersection of note and CAD pattern, i.e., the candidate of {bend, slide, pull-off, hammer-on, normal})
        """
        ascending_candidate, ascending_candidate_note, non_candidate_ascending_note = candidate_selection(expression_style_note[:,0:3], short_ascending_pattern)
        # num_valid_candidate, num_invalid_candidate, invalid_candidate, TP_bend, TP_slide, TP_hamm, FN_bend, FN_slide, FN_hamm = short_pattern_evaluate(ascending_candidate,FN_bend,FN_slide,join(hamm_answer_dir,name_ext))   
        descending_candidate, descending_candidate_note, non_candidate_descending_note = candidate_selection(expression_style_note[:,0:3], short_descending_pattern)
        # num_valid_candidate, num_invalid_candidate, invalid_candidate, TP_release, TP_slide, TP_pull, FN_release, FN_slide, FN_pull = short_pattern_evaluate(descending_candidate,FN_release,FN_slide,join(pull_answer_dir,name_ext))
        # save result: candidate
        np.savetxt(args.output_dir+os.sep+name+'.ascending.candidate',ascending_candidate, fmt='%s')
        np.savetxt(args.output_dir+os.sep+name+'.descending.candidate',descending_candidate, fmt='%s')
        
        """
        S2.4 Extract raw audio features of candidate regions
        """
        # load audio
        audio = MonoLoader(filename = f)()
        # processing
        print '     Processing file: ', f
        candidate_type = ['ascending','descending']
        # loop in ascending and descending candidate list
        for ct in candidate_type:
            print '         EXtracting features from ', ct, ' candadites...'
            # candidate file path
            candidate_path = args.output_dir+os.sep+name+'.'+ct+'.candidate'
            # inspect if candidate file exist and load it
            try:
                candidate = np.loadtxt(candidate_path)
            except IOError:
                print 'The candidate of ', name, ' doesn\'t exist!'
            # reshape candidate if it is in one dimension
            if candidate.shape==(2,): candidate = candidate.reshape(1,2)
            # convert seconds into samples
            candidate_sample = candidate*contour_sr
            # create feature matrix
            feature_vec_all = np.array([])
            # loop in candidates
            for c in candidate_sample:
                # clipping audio signal
                audio_clip = audio[c[0]:c[1]]
                # extract features
                feature_vec = feature_extractor(audio=audio_clip, features=selected_features)
                feature_vec_all = np.concatenate((feature_vec_all,feature_vec), axis = 0)            
            # reshpe feature vector and save result
            if feature_vec_all.size!=0:
                feature_vec_all = feature_vec_all.reshape(len(candidate_sample),len(feature_vec_all)/len(candidate_sample))
                np.savetxt(args.output_dir+os.sep+name+'.'+ct+'.candidate'+'.raw.feature', feature_vec_all, fmt='%s')

        """
        S2.5 Classfication 
        """        
        # load pre-trained SVM
        model = fnmatch.filter(glob.glob(args.input_model+os.sep+'/*'), '*'+'.model.npy')
        clf = np.load(model[0]).item()

        # load raw features 
        clf = np.load(args.model+os.sep+'test_save_model.npy').item()

        # data preprocessing



        # classfication
        y_pred = clf.predict(feature_vec_all)
        print y_pred


if __name__ == '__main__':
    args = parser()
    main(args)