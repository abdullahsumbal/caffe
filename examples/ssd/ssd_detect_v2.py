#encoding=utf8
'''
Detection with SSD
In this example, we will load a SSD model and use it to detect objects.
'''

import os
import sys
import json
import glob
import argparse
import numpy as np
from os import listdir
from os.path import isfile, join
from datetime import datetime
from PIL import Image, ImageDraw

# To hide the log
os.environ['GLOG_minloglevel'] = '3'

# Make sure that caffe is on the python path:
caffe_root = '/home/sumbal/Desktop/Single_Shot_Multibox_Detection_Counter/'
os.chdir(caffe_root)
sys.path.insert(0, os.path.join(caffe_root, 'python'))
import caffe

from google.protobuf import text_format
from caffe.proto import caffe_pb2


def get_labelname(labelmap, labels):
    num_labels = len(labelmap.item)
    labelnames = []
    if type(labels) is not list:
        labels = [labels]
    for label in labels:
        found = False
        for i in xrange(0, num_labels):
            if label == labelmap.item[i].label:
                found = True
                labelnames.append(labelmap.item[i].display_name)
                break
        assert found == True
    return labelnames

class CaffeDetection:
    def __init__(self, gpu_id, model_def, model_weights, image_resize, labelmap_file):
        # caffe.set_device(gpu_id)
        # caffe.set_mode_gpu()

        self.image_resize = image_resize
        # Load the net in the test phase for inference, and configure input preprocessing.
        self.net = caffe.Net(model_def,      # defines the structure of the model
                             model_weights,  # contains the trained weights
                             caffe.TEST)     # use test mode (e.g., don't perform dropout)
         # input preprocessing: 'data' is the name of the input blob == net.inputs[0]
        self.transformer = caffe.io.Transformer({'data': self.net.blobs['data'].data.shape})
        self.transformer.set_transpose('data', (2, 0, 1))
        self.transformer.set_mean('data', np.array([104, 117, 123])) # mean pixel
        # the reference model operates on images in [0,255] range instead of [0,1]
        self.transformer.set_raw_scale('data', 255)
        # the reference model has channels in BGR order instead of RGB
        self.transformer.set_channel_swap('data', (2, 1, 0))

        # load PASCAL VOC labels
        file = open(labelmap_file, 'r')
        self.labelmap = caffe_pb2.LabelMap()
        text_format.Merge(str(file.read()), self.labelmap)

    def detect(self, image_file, conf_thresh=0.5, topn=5):
        '''
        SSD detection
        '''
        # set net to batch size of 1
        # image_resize = 300
        self.net.blobs['data'].reshape(1, 3, self.image_resize, self.image_resize)
        image = caffe.io.load_image(image_file)

        #Run the net and examine the top_k results
        transformed_image = self.transformer.preprocess('data', image)
        self.net.blobs['data'].data[...] = transformed_image

        # Forward pass.
        detections = self.net.forward()['detection_out']

        # Parse the outputs.
        det_label = detections[0,0,:,1]
        det_conf = detections[0,0,:,2]
        det_xmin = detections[0,0,:,3]
        det_ymin = detections[0,0,:,4]
        det_xmax = detections[0,0,:,5]
        det_ymax = detections[0,0,:,6]

        # Get detections with confidence higher than 0.6.
        top_indices = [i for i, conf in enumerate(det_conf) if conf >= conf_thresh]

        top_conf = det_conf[top_indices]
        top_label_indices = det_label[top_indices].tolist()
        top_labels = get_labelname(self.labelmap, top_label_indices)
        top_xmin = det_xmin[top_indices]
        top_ymin = det_ymin[top_indices]
        top_xmax = det_xmax[top_indices]
        top_ymax = det_ymax[top_indices]

        result = []
        for i in xrange(min(topn, top_conf.shape[0])):
            xmin = top_xmin[i] # xmin = int(round(top_xmin[i] * image.shape[1]))
            ymin = top_ymin[i] # ymin = int(round(top_ymin[i] * image.shape[0]))
            xmax = top_xmax[i] # xmax = int(round(top_xmax[i] * image.shape[1]))
            ymax = top_ymax[i] # ymax = int(round(top_ymax[i] * image.shape[0]))
            score = top_conf[i]
            label = int(top_label_indices[i])
            label_name = top_labels[i]
            result.append([xmin, ymin, xmax, ymax, label, score, label_name])
        return result


def main(args):
    '''main '''
    detection = CaffeDetection(args.gpu_id,
                               args.model_def, args.model_weights,
                               args.image_resize, args.labelmap_file)

    print(glob.glob(args.test_bulk))
    # Set up : TODO

    # Iterate images
    with open(args.test_bulk) as f:
        config_data = json.load(f)
        images_dir = str(config_data['root_dir'])
        levels = config_data['levels']
        # Iterate all levels
        for level_key, level_value in levels.iteritems():

            if level_value['run'] == False:
                print 'Skipping level: ', str(level_key)
                continue
            print 'Testing level: ', str(level_key)
            level_dir = images_dir + '/' + str(level_key)

            # iterate all resolution in each level
            for resolution_key, resolution_value in level_value['resolution'].iteritems():
                if resolution_value['run'] == False:
                    print 'Skipping resolution: ', str(resolution_key)
                    continue
                print 'Testing resolution: ', str(resolution_key)
                resolution_dir = level_dir + '/' + str(resolution_key)
                os.chdir(resolution_dir)
                # Iterate all images
                for counter, image_name in enumerate(listdir(resolution_dir)):
                    if isfile(join(resolution_dir, image_name)) and '.jpg' in image_name:
                        # Make a file to keep record of data for each image file
                        output_dir = join(resolution_dir, 'output')
                        if not os.path.exists(output_dir):
                            os.makedirs(output_dir)
                        image_data = open(join(output_dir, image_name + '_data'), "a")
                        image_path = join(resolution_dir, image_name)
                        # Start detection
                        start = datetime.now()
                        print(image_path)
                        result = detection.detect(image_path)
                        # End detection
                        runtime = (datetime.now() - start).total_seconds()
                        img = Image.open(image_path)
                        draw = ImageDraw.Draw(img)
                        width, height = img.size

                        # Setting up variables.
                        total_confidence_person = 0
                        total_confidence_dog = 0
                        total_confidence_bicycle = 0
                        avg_confidence_person = 0
                        avg_confidence_bicycle = 0
                        avg_confidence_dog = 0
                        ssd_detected_person = 0
                        ssd_detected_dog = 0
                        ssd_detected_bicycle = 0
                        object_counter = 0

                        for item in result:
                            xmin = int(round(item[0] * width))
                            ymin = int(round(item[1] * height))
                            xmax = int(round(item[2] * width))
                            ymax = int(round(item[3] * height))
                            draw.rectangle([xmin, ymin, xmax, ymax], outline=(255, 0, 0))
                            draw.text([xmin, ymin], item[-1] + str(item[-2]) +" runtime: " + str(runtime), (0, 0, 255))
                            # Record data for each image
                            # Count people and Sum confidence of person
                            if item[-1] == 'person':
                                object_counter += 1
                                total_confidence_person += item[-2]
                                ssd_detected_person += 1
                                image_data.write('object {}: {} \n'.format(object_counter, item[-1]))
                                image_data.write('confidence : {}\n'.format(str(item[-2])))
                                image_data.write('xmin={},ymin={},xmax={},ymax={} \n'.format(xmin, ymin, xmax, ymax))
                            # Count dogs and Sum confidence of dog
                            if item[-1] == 'dog':
                                object_counter += 1
                                total_confidence_dog += item[-2]
                                ssd_detected_dog += 1
                                image_data.write('object {}: {} \n'.format(object_counter, item[-1]))
                                image_data.write('confidence : {}\n'.format(str(item[-2])))
                                image_data.write('xmin={},ymin={},xmax={},ymax={} \n'.format(xmin, ymin, xmax, ymax))
                            # Count dogs and Sum confidence of dog
                            if item[-1] == 'bicycle':
                                object_counter += 1
                                total_confidence_bicycle += item[-2]
                                ssd_detected_bicycle += 1
                                image_data.write('object {}: {} \n'.format(object_counter, item[-1]))
                                image_data.write('confidence : {}\n'.format(str(item[-2])))
                                image_data.write('xmin={},ymin={},xmax={},ymax={} \n'.format(xmin, ymin, xmax, ymax))
                        image_data.write('runtime : {}\n'.format(runtime))
                        img.save(resolution_dir+'/output/' + image_name)
                        # Prevent zero error.
                        if ssd_detected_person != 0:
                            avg_confidence_person = (total_confidence_person / ssd_detected_person)
                        if ssd_detected_dog != 0:
                            avg_confidence_dog = (total_confidence_dog / ssd_detected_dog)
                        if ssd_detected_bicycle != 0:
                            avg_confidence_bicycle = (total_confidence_bicycle / ssd_detected_bicycle)
                        # write data to file
                        with open(resolution_dir+'/output/results.txt', 'a') as results_file:
                            string = "{},{},{},{},{},{},{},{}\n".format(
                                image_name,
                                str(runtime),
                                str(ssd_detected_person),
                                str(ssd_detected_dog),
                                str(ssd_detected_bicycle),
                                str(avg_confidence_person),
                                str(avg_confidence_dog),
                                str(avg_confidence_bicycle)
                            )
                            results_file.write(string)
                        results_file.close()


def parse_args():
    '''parse args'''
    parser = argparse.ArgumentParser()
    parser.add_argument('--gpu_id', type=int, default=0, help='gpu id')
    parser.add_argument('--labelmap_file',
                        default='data/VOC0712/labelmap_voc.prototxt')
    parser.add_argument('--model_def',
                        default='models/VGGNet/VOC0712/SSD_300x300/deploy.prototxt')
    parser.add_argument('--image_resize', default=300, type=int)
    parser.add_argument('--model_weights',
                        default='models/VGGNet/VOC0712/SSD_300x300/'
                        'VGG_VOC0712_SSD_300x300_iter_120000.caffemodel')
    parser.add_argument('--image_file', default='examples/images/fish-bike.jpg')
    parser.add_argument('--test_bulk', default='config/test_config_v2.json')
    return parser.parse_args()


if __name__ == '__main__':
    main(parse_args())
