#!/usr/bin/env python
# encoding: utf-8
"""
Author: Yuan-Ping Chen
Data: 2016/02/07
----------------------------------------------------------------------
Candidate Selection
----------------------------------------------------------------------
Args:
    input_melody:       Text files of pitch series to be processed.
    input_note:         Note events to be processed.
    output_dir:         Directory for storing the results.

Optional args:
    Please refer to --help.
----------------------------------------------------------------------
Returns:
    Candidate:          candidate time segment of guitar expression 
                        style.

"""
import glob, os, sys
import numpy as np
import math
from scipy.io import wavfile
from GuitarTranscription_parameters import *

def continuously_ascending_descending_pattern(melody,direction,MinLastingDuration,MaxPitchDifference,MinPitchDifference,hop,sr):
    """
    Find continuously ascending or descending pattern in melody contour.
    Usage:
    :param melody:                melody contour(MIDI number).
    :param direction:             find continuously ascending or descending pattern.
    :param MinLastingDuration:    minimal duration the onset frame and offset frame in second.
    :param MinPitchDifference:    minimal differnce of pitch value(in semitone) between the onset frame and offset frame.
    :param hop:                   the step size of the melody contour.
    :param sr:                    the sampling rate of the melody contour.

    """
    import operator
    if direction=='up':
        op = operator.ge
        opt = operator.gt
    elif direction=='down':
        op = operator.le
        opt = operator.lt
    else:
        print "Direction must either be \'up\' or \'down\'"
    contour = melody.copy()
    pattern = np.empty([0,2])
    pattern_pitch_contour = np.zeros(np.shape(contour))
    MinLastingFrame = MinLastingDuration*sr/hop
    # Find all segments with pitch sequence pattern continuesly ascending or descending 
    for f in range(contour.shape[0]-1):
        if contour[f] != 0:
            Start = f
            FrameNow = f
            while op(contour[FrameNow+1],contour[FrameNow]) and \
                    abs(contour[FrameNow]-contour[FrameNow+1]) < 0.5 and \
                    FrameNow+1<contour.shape[0]-1:
                if opt(contour[FrameNow+1],contour[FrameNow]):
                    FrameNow = FrameNow+1
                else:
                    count=0
                    Check = FrameNow
                    while contour[Check+1]==contour[Check]:
                        Check+=1
                        count+=1
                    if count<=16:
                        FrameNow = FrameNow+count
                    else:
                        contour[FrameNow+1:Check+1] = 0
                        break
            # if the length of ascending pitch is larger than the threhsold
            if (FrameNow-Start+1)>=MinLastingFrame and \
                abs(contour[FrameNow]-contour[Start]) >= MinPitchDifference and \
                abs(contour[FrameNow]-contour[Start]) <= MaxPitchDifference:
                pattern_pitch_contour[Start:FrameNow+1] = contour[Start:FrameNow+1]
                # BendPredRaw = [BendPredRaw; Start FrameNow PCLabel(Start) PCLabel(FrameNow)]
                pattern = np.append(pattern,[[Start,FrameNow+1]],axis=0)
            contour[Start:FrameNow+1] = 0
    pattern = pattern*hop/sr
    return pattern, pattern_pitch_contour

def candidate_selection(note, short_CAD_pattern):
    """
    Candidate selection for bend and slide by rules.
    All the candidates must meet: 
        i) continuously ascending or descending pattern covers three note.
        ii) The pitch difference of the three covered notes is a semitone
    :input note:        2-D ndarray:[pitch(MIDI). onset(s). duration(s)] notes after mergin vibrato
    :input CAD_pattern: 1-D ndarray[onset(s). offset(s).]                continuously ascending or descending pattern
    :output CAD_pattern: 1-D ndarray[onset(s). offset(s).]               continuously ascending or descending pattern
    :output note_of_long_CAD: 1-D ndarray[onset(s). offset(s).]                  continuously ascending or descending pattern
    """
    candidate_note_index = []
    candidate_pattern_index = []
    pseudo_CAD = short_CAD_pattern.copy()
    pseudo_note = note.copy()
    # Loop in each pattern
    for p in range(pseudo_CAD.shape[0]):
        onset_pattern = pseudo_CAD[p,0]
        offset_pattern = pseudo_CAD[p,1]
        # Loop in each note
        for n in range(pseudo_note.shape[0]):
            onset_first_note = pseudo_note[n,1]
            offset_first_note = pseudo_note[n,1]+pseudo_note[n,2]
            # Find notes where pattern located
            if onset_pattern >= onset_first_note and onset_pattern <= offset_first_note:
                if n+1>=pseudo_note.shape[0]:
                        break
                m = n+1
                if offset_pattern >= pseudo_note[m,1] and offset_pattern <= pseudo_note[m,1]+pseudo_note[m,2] and \
                    abs(pseudo_note[m,0]-pseudo_note[n,0])<=3 and \
                    pseudo_note[m,1]-(pseudo_note[n,1]+pseudo_note[n,2])<0.05:
                    candidate_note_index.append(n)
                    candidate_note_index.append(m)
                    candidate_pattern_index.append(p)               
    candidate = pseudo_CAD[candidate_pattern_index,:]
    candidate_note = pseudo_note[candidate_note_index,:]
    non_candidate_note = np.delete(pseudo_note,candidate_note_index,axis=0)
    return candidate, candidate_note, non_candidate_note

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
    p.add_argument('input_melody', type=str, metavar='input_melody',
                   help='melody contours to be processed')
    p.add_argument('input_note', type=str, metavar='input_note',
                   help='note events to be processed')
    p.add_argument('output_dir', type=str, metavar='output_dir',
                   help='output directory.')
    # version
    p.add_argument('--version', action='version',
                   version='%(prog)spec 1.03 (2016-03-07)')
    # parse arguments
    args = p.parse_args()

    # return args
    return args
    

def main(args):
    print 'Running candidate selection...'
    
    # parse and list files to be processed
    melody_files = parse_input_files(args.input_melody, ext='.MIDI.smooth.melody')
    
    # create result directory
    if not os.path.exists(args.output_dir): os.makedirs(args.output_dir)
    print '  Output directory: ', '\n', '    ', args.output_dir

    # processing
    for f in melody_files:
        # parse file name and extension
        ext = os.path.basename(f).split('.')[-1]
        name = os.path.basename(f).split('.')[0]

        # load melody 
        try:
            MIDI_smooth_melody = np.loadtxt(f)
        except IOError:
            print 'The melody contour of ', name, ' doesn\'t exist!'

        # load note
        note_path = args.input_note+os.sep+name+'.pruned.note'
        try:
            pruned_note = np.loadtxt(note_path)
        except IOError:
            print 'The note event of ', name, ' doesn\'t exist!'

        """
        Find continuously ascending/descending (CAD) F0 sequence patterns
        """
        # find continuously ascending (CAD) F0 sequence patterns
        ascending_pattern, ascending_pitch_contour = continuously_ascending_descending_pattern(
                                MIDI_smooth_melody,direction='up',MinLastingDuration=0.05, 
                                MaxPitchDifference = 3.8, MinPitchDifference=0.8,hop=contour_hop,sr=contour_sr)
        # find continuously descending (CAD) F0 sequence patterns
        descending_pattern, descending_pitch_contour = continuously_ascending_descending_pattern(
                                MIDI_smooth_melody,direction='down',MinLastingDuration=0.05, 
                                MaxPitchDifference = 3.8, MinPitchDifference=0.8,hop=contour_hop,sr=contour_sr)

        # save result: CAD F0 sequence pattern
        np.savetxt(args.output_dir+os.sep+name+'.ascending.pattern',ascending_pattern, fmt='%s')
        np.savetxt(args.output_dir+os.sep+name+'.ascending.pitch_contour',ascending_pitch_contour, fmt='%s')
        np.savetxt(args.output_dir+os.sep+name+'.descending.pattern',descending_pattern, fmt='%s')
        np.savetxt(args.output_dir+os.sep+name+'.descending.pitch_contour',descending_pitch_contour, fmt='%s')

        """
        Find intersection of note and pattern of {bend,slide,pull-off,hammer-on,normal})
        """
        # candidate selection
        ascending_candidate, ascending_candidate_note, non_candidate_ascending_note = candidate_selection(pruned_note, ascending_pattern)
        descending_candidate, descending_candidate_note, non_candidate_descending_note = candidate_selection(pruned_note, descending_pattern)
        # save result: candidate
        np.savetxt(args.output_dir+os.sep+name+'.ascending.candidate',ascending_candidate, fmt='%s')
        np.savetxt(args.output_dir+os.sep+name+'.descending.candidate',descending_candidate, fmt='%s')

if __name__ == '__main__':
    args = parser()
    main(args)