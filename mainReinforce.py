# -*- coding: utf-8 -*-
"""
Created on Fri Oct 18 19:39:49 2019

@author: Tiago
"""
import os
import tensorflow as tf
from keras import backend as K
from reinforce import Reinforcement
from keras.models import Sequential
from model import Model 
from prediction import Predictor
from predictSMILES import *
from utils import *
import numpy as np


config_file = 'configReinforce.json' # Configuration file
property_identifier = 'a2d' # It can be 'a2d', kor', 'qed', 'sas', 'logP', or 'jak2'

os.environ["CUDA_VISIBLE_DEVICES"]="0"
session = tf.compat.v1.Session()
K.set_session(session)
 
def main():
        
    """
    Main routine
    """
    # load configuration file
    configReinforce,exp_time=load_config(config_file)
    
    # Load generator object
    generator_model = Sequential()
    generator_model = Model(configReinforce)
    generator_model.model.load_weights(configReinforce.model_name_unbiased)

    # Initialize lists to evaluate the model
    difs = [] # List with the differences between the averages of the desired property distributions (G_0 and G_optimized)
    divs = [] # List with the internal diversities of the G_optimized generated molecules 
    perc_valid = [] # List with the % of valid SMILES generated by G_optimized
    
    # To compute SA score or qed it's not necessary to have a Predictor model
    if property_identifier != 'sas' and property_identifier != 'qed':
        # Load the Predictor object
        predictor = Predictor(configReinforce,property_identifier)
    else:
        predictor = None
  
    # Create Reinforcement Learning object
    RL_obj = Reinforcement(generator_model, predictor,configReinforce,property_identifier)
    
    # SMILES generation with unbiased Generator 
#    smiles_original, prediction_original,valid,unique,div = RL_obj.test_generator(configReinforce.n_to_generate,0,True)
    
#      Training Generator with RL    
#    RL_obj.policy_gradient()
    
    # SMILES generation after 85 training iterations 
    smiles_iteration85,prediction_iteration85,valid,unique,div,perc_desirable = RL_obj.test_generator(configReinforce.n_to_generate,85, False)
   
    # Plot to evaluate the differences before and after perform the RL training step
#    plot_evolution(prediction_original,prediction_iteration85,property_identifier)
    
    # To directly compare the original and biased models several times, evaluating
    # prediction differences, diversity, and validity
    for k in range(20):
        print("BIASED GENERATION: " + str(k))
        dif,div,valid,perc_uniq,perc_desirable = RL_obj.compare_models(configReinforce.n_to_generate,True)
        difs.append(dif)
        divs.append(div)
        perc_valid.append(valid)
    print("Mean value difference: " + str(np.mean(difs)))
    print("Mean value diversity: " + str(np.mean(divs)))
    print("Mean value validity: " + str(np.mean(perc_valid)))
if __name__ == '__main__':
    main()