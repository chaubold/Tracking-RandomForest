import vigra
import matplotlib.pyplot as plt
from vigra import numpy as np
import h5py
from sklearn.neighbors import KDTree
from sklearn.cross_validation import KFold
from sklearn.metrics import precision_recall_fscore_support
from compiler.ast import flatten

#read in 'n2-n1' of images
def read_in_images(n1,n2, filepath):
    gt_labelimage_filename = [0]*(n2-n1)
    for i in range(n1,n2):
        if i<10:
            gt_labelimage_filename[i-n1] = str(filepath)+'0000'+str(i)+'.h5'
        else:
            gt_labelimage_filename[i-n1] = str(filepath)+'000'+str(i)+'.h5'
    gt_labelimage = [vigra.impex.readHDF5(gt_labelimage_filename[i], 'segmentation/labels') for i in range(0,n2-n1)]
    return gt_labelimage

#compute features from input data and return them
def compute_features(raw_image, labeled_image, n1, n2):
    #perhaps there is an elegant way to get into the RegionFeatureAccumulator. For now, the new feature are a seperate vector
    features = [0]*(n2-n1)
    allFeat = [0]*(n2-n1)
    for i in range(0,n2-n1):
        features[i] = vigra.analysis.extractRegionFeatures(raw_image[:,:,i,0].astype('float32'),labeled_image[i][:,:,0], ignoreLabel=0)
        tempnew1 = vigra.analysis.extractConvexHullFeatures(labeled_image[i][:,:,0].squeeze().astype(np.uint32), ignoreLabel=0)
        tempnew2 = vigra.analysis.extractSkeletonFeatures(labeled_image[i][:,:,0].squeeze().astype(np.uint32))
        allFeat[i] = dict(features[i].items()+tempnew1.items()+tempnew2.items())
    return allFeat

#return a feature vector of two objects (f1-f2,f1*f2)
def getFeatures(f1,f2,o1,o2): #what to do with NaNs?
    res=[]; res2=[]
    for key in f1:
        if key == "Global<Maximum >" or key=="Global<Minimum >": #this ones have only one element
            res.append(f1[key]-f2[key])
            res2.append(f1[key]*f2[key])
        elif key == 'RegionCenter':
            res.append(np.linalg.norm(f1[key][o1]-f2[key][o2])) #difference of features
            res2.append(np.linalg.norm(f1[key][o1]*f2[key][o2])) #product of features
        elif key=='Histogram': #contains only zeros, so trying to see what the prediction is without it
            continue
        elif key == 'Polygon': #vect has always another length for different objects, so center would be relevant
            continue
        else:
            res.append((f1[key][o1]-f2[key][o2]).tolist() )  #prepare for flattening
            res2.append((f1[key][o1]*f2[key][o2]).tolist() )  #prepare for flattening
    x= np.asarray(flatten(res)) #flatten
    x2= np.asarray(flatten(res2)) #flatten
    #x= x[~np.isnan(x)]
    #x2= x2[~np.isnan(x2)] #not getting the nans out YET
    return np.concatenate((x,x2))

#read in 'n2-n1' of labels
def read_positiveLabels(n1,n2, filepath):
    gt_labels_filename = [0]*(n2-n1)
    for i in range(n1+1,n2 ): #the first one contains no moves data
        if i<10:
            gt_labels_filename[i-n1] = str(filepath)+'0000'+str(i)+'.h5'
        else:
            gt_labels_filename[i-n1] = str(filepath)+'000'+str(i)+'.h5'
    gt_labelimage = [vigra.impex.readHDF5(gt_labels_filename[i], 'tracking/Moves') for i in range(1,n2-n1)]
    return gt_labelimage

# compute negative labels by nearest neighbor
def negativeLabels(features, positiveLabels):
    neg_lab = [[]]*len(features)
    for i in range(1, len(features)):
        kdt = KDTree(features[i]['RegionCenter'], metric='euclidean')
        neighb = kdt.query(features[i-1]['RegionCenter'], k=3, return_distance=False)
        for j in range(1, len(features[i])):
            for m in range(0, neighb.shape[1]):
                neg_lab[i].append([j,neighb[j][m]])
    return neg_lab

def allFeatures(features, labels, neg_labels):
    j=0
    lab=[]
    for i in range(0,len(features)-1):
        for k in labels[i]:
            if j == 0:
                x = getFeatures(features[i],features[i+1],k[0],k[1])
                j+=1
            else:
                x = np.vstack((x,getFeatures(features[i],features[i+1],k[0],k[1])))
            lab.append(1)
        for k in neg_labels[i]:
            if k not in labels[i].tolist():
                x = np.vstack((x,getFeatures(features[i],features[i+1],k[0],k[1])))
                lab.append(0)
    x = x[:,~np.isnan(x).any(axis=0)] #now removing the nans
    return x,np.asarray(lab)

def allFeatures_random_neg(features, labels, n_neg):
    j=0
    for i in range(0,len(features)-1):
        for k in labels[i]:
            if j == 0:
                x = getFeatures(features[i],features[i+1],k[0],k[1])
                j+=1
            else:
                x = np.vstack((x,getFeatures(features[i],features[i+1],k[0],k[1])))
        #negative examples
        count_negative = 0
        while(count_negative < n_neg):
            m = np.random.randint(1, max(labels[i][0])-10,size=2)
            if m not in labels[i]:
                count_negative+=1
                x = np.vstack((x,getFeatures(features[i],features[i+1],m[0],m[1])))
    return x

def TrainRF(filepath, gt_rawimage_filename, initFrame, endFrame, outputFilename):
    gt_rawimage = vigra.impex.readHDF5(gt_rawimage_filename, 'volume/data')
    features = compute_features(gt_rawimage, read_in_images(initFrame, endFrame, filepath), initFrame, endFrame)
    mylabels = read_positiveLabels(initFrame,endFrame,filepath)
    neg_labels = negativeLabels(features,mylabels)
    mydata, endlabels =  allFeatures(features, mylabels, neg_labels)
    rf = vigra.learning.RandomForest()
    rf.learnRF(mydata.astype("float32"), (np.asarray(endlabels)).astype("uint32").reshape(-1,1))
    rf.writeHDF5(outputFilename)
    #return rf

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="trainRF")
    parser.add_argument("filepath",
                        help="read from filepath", metavar="FILE")

    parser.add_argument("rawimage_filename",
                        help="filepath+name of the raw image", metavar="FILE")
    parser.add_argument("initFrame", default=0, type=int, 
                        help="where to begin reading the frames")
    parser.add_argument("endFrame", default=0, type=int, 
                        help="where to end frames")
    parser.add_argument("outputFilename",
                        help="save RF into file", metavar="FILE")
    args = parser.parse_args()
    TrainRF(args.filepath, args.rawimage_filename, args.initFrame, args.endFrame, args.outputFilename) #writes learned RF to disk

    #initFrame = 0
    #endFrame = 20

    #read in raw images  - here ALL
    #filepath = '/net/hciserver03/storage/lparcala/mitocheck_006--01--06/manual_tracking2/'
    #gt_rawimage_filename = '/net/hciserver03/storage/lparcala/mitocheck_006--01--06/mitocheck_94570_2D+t_00-92.h5'
    
	#TrainRF(filepath, rawimage_filename, initFrame, endFrame) #returns learned RF
