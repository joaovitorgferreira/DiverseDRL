# -*- coding: utf-8 -*-
"""
Created on Sat Oct 26 00:39:28 2019

@author: Tiago
"""
from rdkit import Chem
import tensorflow as tf
from prediction import *
import numpy as np
from Smiles_to_tokens import SmilesToTokens
from predictSMILES import *
from model import Model 
from tqdm import tqdm
from utils import * 
from tqdm import trange
from keras.models import Sequential
from keras import losses
import keras.backend as K
from keras import optimizers
from rdkit.Chem.Draw import DrawingOptions
from rdkit.Chem import Draw

sess = tf.compat.v1.InteractiveSession()            
       
class Reinforcement(object):
    def __init__(self, generator, predictor, configReinforce):  
        """
        Constructor for the Reinforcement object.
        Parameters
        ----------
        generator: generative model object that produces string of characters 
            (trajectories)
        predictor: object of any predictive model type
            predictor accepts a trajectory and returns a numerical
            prediction of desired property for the given trajectory
        configReinforce: bunch
            Configuration file containing all the necessary specification and
            parameters. 
        Returns
        -------
        object Reinforcement used for implementation of Reinforcement Learning 
        model to bias the Generator
        """

        super(Reinforcement, self).__init__()
        self.generator_unbiased = generator
        self.generator_biased = generator
        self.generator = generator
        self.configReinforce = configReinforce
        self.generator_unbiased.model.load_weights(self.configReinforce.model_name_unbiased)
        self.generator_biased.model.load_weights(self.configReinforce.model_name_unbiased)
        self.token_table = SmilesToTokens()
        self.table = self.token_table.table
        self.predictor = predictor
        self.get_reward_MO = get_reward_MO
        self.threshold_greedy = 0.1
        self.n_table = len(self.token_table.table)
        self.preds_range = [3.0,1.381,1.284,1.015] #3.2,1.29
        self.best_model = '4'
#        self.adam = optimizers.Adam(learning_rate=0.0001, beta_1=0.9, beta_2=0.999, amsgrad=False)
        self.adam = optimizers.Adam()
        self.scalarization_mode = 'linear' # it can be 'linear', 'ws_linear', or 'chebyshev'

    def custom_loss(self,magic_matrix):
        def lossfunction(y_true,y_pred):
#            return (1/10)* K.sum(((tf.compat.v1.math.log_softmax(y_pred))*y_true)*magic_matrix)
            return (1/self.configReinforce.batch_size)*K.sum(losses.categorical_crossentropy(y_true,y_pred)*magic_matrix)
       
        return lossfunction

    def get_policy_model(self,aux_array):

        self.generator_biased = Sequential()
        self.generator_biased = Model(self.configReinforce) 
        self.generator_biased.model.compile(
                optimizer=self.adam,
                loss = self.custom_loss(aux_array))
        
        return self.generator_biased.model
        

    def policy_gradient(self, gamma=0.97):    
        """
        Implementation of the policy gradient algorithm.

        Parameters:
        -----------
        self.n_batch: int
            number of trajectories to sample per batch.    
        gamma: float (default 0.97)
            factor by which rewards will be discounted within one trajectory.
            Usually this number will be somewhat close to 1.0.

        Returns
        -------
        This function returns, at each iteration, the graphs with average 
        reward and averaged loss from the batch of generated trajectories 
        (SMILES). Moreover it returns the average reward for QED and KOR properties.
        Also, it returns the used weights and the averaged scaled reward for
         """
         
        pol = 9
        cumulative_rewards = []
        cumulative_rewards_kor = []
        cumulative_rewards_qed = [] 
        last_3_weights = []
        previous_weights = []
        keepSearch = True
        while keepSearch:
            weights,previous_weights,last_3_weights,keepSearch = searchWeights(pol,cumulative_rewards,previous_weights,last_3_weights,self.scalarization_mode)

            # Initialize the variable that will contain the output of each prediction
            dimen = len(self.table)
            states = np.empty(0).reshape(0,dimen)
            pol_rewards_kor = []
            pol_rewards_qed = []
            all_rewards = []
            all_losses = []
            # Re-compile the model to adapt the loss function and optimizer to the RL problem
            self.generator_biased.model = self.get_policy_model(np.arange(43))
            self.generator_biased.model.load_weights(self.configReinforce.model_name_unbiased)
            for i in range(self.configReinforce.n_iterations):
                
#                    if self.scalarization_mode == 'chebyshev':
#                    preds_range = generation(self.generator_biased,self.predictor,self.configReinforce)
#                    else:
#                        preds_range = -1

                for j in trange(self.configReinforce.n_policy, desc='Policy gradient progress'):
                    
                    cur_reward = 0
                    cur_reward_qed = 0
                    cur_reward_kor = 0
                    
                    # Necessary object to transform new generated smiles to one-hot encoding
                    token_table = SmilesToTokens()
                    aux_matrix = np.zeros((65,1))
                    
                    ii = 0
                    for _ in range(self.configReinforce.batch_size):
                    
                        # Sampling new trajectory
                        reward = 0
                        reward_kor = 0
                        reward_qed = 0
                       
                        while reward == 0:
                            predictSMILES =  PredictSMILES(self.generator_unbiased,self.generator_biased,True,self.threshold_greedy,self.configReinforce) # generate new trajectory
                            trajectory = predictSMILES.sample() 
           
                            try:                     
                                s = trajectory[0] # because predictSMILES returns a list of smiles strings
                                if 'A' in s: # A is the padding character
                                    s = remove_padding(trajectory[0])
                                    
                                print("Validation of: ", s) 
            
                                mol = Chem.MolFromSmiles(s)
             
                                trajectory = 'G' + Chem.MolToSmiles(mol) + 'E'
#                                trajectory = 'GCCE'
                            
                                reward_kor,reward_qed = self.get_reward_MO(self.predictor,trajectory[1:-1])
                                print(reward_kor,reward_qed)
                                reward = scalarization(reward_kor,reward_qed,self.scalarization_mode,weights,self.preds_range)
                                
                                if len(trajectory) > 65:
                                    reward = 0
                                print(reward)
                               
                            except:
                                reward = 0
                                print("\nInvalid SMILES!")
            
                        # Converting string of characters to one-hot enconding
                        trajectory_input,_ = token_table.one_hot_encode(token_table.tokenize(trajectory))
                        ti,_ = token_table.one_hot_encode(token_table.tokenize(trajectory))
                        discounted_reward = reward
                        cur_reward += reward
                        cur_reward_kor += reward_kor
                        cur_reward_qed += reward_qed                        
                 
                        # "Following" the trajectory and accumulating the loss
                        idxs = 0
                        for p in range(1,len(trajectory_input[0,:,])):
                            
                            state = []
                            state = np.reshape(trajectory_input[0,p,:], [1, dimen])
                            idx = np.nonzero(state)
                            state[idx] = state[:,idx[1]]*discounted_reward
#                            output = self.generator_biased.model.predict(trajectory_input[:,0:p,:])
#
                            inp = ti[:,0:p,:]
                  
                            inp_p = padding_one_hot(inp,self.table) # input to padd
                            mat = np.zeros((1,65))
                            mat[:,idxs] = 1

                            if ii == 0:
                                inputs = inp_p
                                aux_matrix = mat
                            else:
                                inputs = np.dstack([inputs,inp_p])
                                aux_matrix = np.dstack([aux_matrix,mat])
            
                            discounted_reward = discounted_reward * gamma
                            
                            states = np.vstack([states, state])
                            ii += 1
                            idxs += 1
                            
                    # Doing backward pass and parameters update
                 
                    states = states[:,np.newaxis,:]
                    inputs = np.moveaxis(inputs,-1,0)

                    aux_matrix = np.squeeze(aux_matrix)
                    aux_matrix = np.moveaxis(aux_matrix,-1,0)
                    
                    self.generator_biased.model.compile(optimizer = self.adam, loss = self.custom_loss(aux_matrix))
                    #update weights based on the provided collection of samples, without regard to any fixed batch size.
                    loss = self.generator_biased.model.train_on_batch(inputs,states) # update the weights with a batch
                    
                    # Clear out variables
                    states = np.empty(0).reshape(0,dimen)
                    inputs = np.empty(0).reshape(0,0,dimen)

                    cur_reward = cur_reward / self.configReinforce.batch_size
                    cur_reward_qed = cur_reward_qed / self.configReinforce.batch_size
                    cur_reward_kor = cur_reward_kor / self.configReinforce.batch_size
               
                    # serialize model to JSON
                    model_json = self.generator_biased.model.to_json()
                    with open(self.configReinforce.model_name_biased + "_"+self.scalarization_mode + '_' +str(pol)+".json", "w") as json_file:
                        json_file.write(model_json)
                    # serialize weights to HDF5
                    self.generator_biased.model.save_weights(self.configReinforce.model_name_biased + "_"+self.scalarization_mode + '_' +str(pol)+".h5")
                    print("Updated model saved to disk")
                    
                    if len(all_rewards) > 2: # decide the threshold of the next generated batch 
                        self.threshold_greedy = compute_thresh(all_rewards[-3:],self.configReinforce.threshold_set)
 
                    all_rewards.append(moving_average(all_rewards, cur_reward)) 
                    pol_rewards_qed.append(moving_average(pol_rewards_qed, cur_reward_qed)) 
                    pol_rewards_kor.append(moving_average(pol_rewards_kor, cur_reward_kor)) 
                    all_losses.append(moving_average(all_losses, loss))
    
                plot_training_progress(all_rewards,all_losses)
                plot_individual_rewds(pol_rewards_qed,pol_rewards_kor)
            cumulative_rewards.append(np.mean(all_rewards[-100:]))
            cumulative_rewards_kor.append(np.mean(pol_rewards_kor[-100:]))
            cumulative_rewards_qed.append(np.mean(pol_rewards_qed[-100:]))
            pol+=1

        plot_MO(cumulative_rewards_qed,cumulative_rewards_kor,cumulative_rewards,previous_weights)
        return cumulative_rewards_qed,cumulative_rewards_kor,cumulative_rewards,previous_weights
    
    def test_generator(self, n_to_generate,iteration, original_model):
        """
        Function to generate molecules with the specified generator model. 

        Parameters:
        -----------

        n_to_generate: Integer that indicates the number of molecules to 
                    generate
        iteration: Integer that indicates the current iteration. It will be 
                   used to build the filename of the generated molecules                       
        original_model: Boolean that specifies generator model. If it is 
                        'True' we load the original model, otherwise, we 
                        load the fine-tuned model 

        Returns
        -------
        The plot containing the distribuiton of the property we want to 
        optimize. It saves one file containing the generated SMILES strings. Also,
        this function returns the SMILES strings, the predictions for KOR affinity
        and QED, and, also, the percentages of valid and unique molecules.
        """
        
        
        if original_model:
             self.generator.model.load_weights(self.configReinforce.model_name_unbiased)
             print("....................................")
             print("original model load_weights is DONE!")
        else:
             self.generator.model.load_weights(self.configReinforce.model_name_biased + "_" + self.scalarization_mode + "_" + self.best_model+ ".h5")
             print("....................................")
             print("updated model load_weights is DONE!")
        
        generated = []
        pbar = tqdm(range(n_to_generate))
        for i in pbar:
            pbar.set_description("Generating molecules...")
            predictSMILES = PredictSMILES(self.generator,None,False,self.threshold_greedy,self.configReinforce)
            generated.append(predictSMILES.sample())
    
        sanitized,valid = canonical_smiles(generated,sanitize=True, throw_warning=False)# validar 
        
        san_with_repeated = []
        for smi in sanitized:
            if len(smi) > 1:
                san_with_repeated.append(smi)
        
        unique_smiles = len(list(np.unique(san_with_repeated))[1:])
        percentage_unq = (unique_smiles/len(san_with_repeated))*100
        
        # prediction pIC50 KOR
        prediction_kor = self.predictor.predict(san_with_repeated)
        
        # prediction qew
        mol_list = smiles2mol(san_with_repeated)
        prediction_qed = qed_calculator(mol_list)
                                                           
        vld = plot_hist(prediction_kor,n_to_generate,valid,"kor")
        vld = plot_hist(prediction_qed,n_to_generate,valid,"qed")
            
        with open(self.configReinforce.file_path_generated + '_' + str(len(san_with_repeated)) + '_iter'+str(iteration)+".smi", 'w') as f:
            for i,cl in enumerate(san_with_repeated):
                data = str(san_with_repeated[i]) + " ," +  str(prediction_kor[i])+ ", " +str(prediction_qed[i]) 
                f.write("%s\n" % data)  
                
        
        return san_with_repeated,prediction_kor,prediction_qed,vld,percentage_unq
                    

    def compare_models(self, n_to_generate,individual_plot):
        """
        Function to generate molecules with the both models

        Parameters:
        -----------
        n_to_generate: Integer that indicates the number of molecules to 
                    generate
                    
        individual_plot: Boolean that indicates if we want to represent the 
                         property distribution of the pre-trained model.

        Returns
        -------
        The plot that contains the distribuitons of the properties we want to 
        optimize originated by the original and fine-tuned models. Besides 
        this, it saves a "generated.smi" file containing the valid generated 
        SMILES and the respective property value in "generated\" folder. Also,
        it returns the differences between the means of the original and biased
        predictions for both properties, the percentage of valid and the 
        internal diversity.
        """

        self.generator.model.load_weights(self.configReinforce.model_name_unbiased)
        print("\n --------- Original model LOADED! ---------")
        
        generated_unb = []
        pbar = tqdm(range(n_to_generate))
        for i in pbar:
            pbar.set_description("Generating molecules...")
            predictSMILES = PredictSMILES(self.generator,None,False,self.threshold_greedy,self.configReinforce)
            generated_unb.append(predictSMILES.sample())
    
        sanitized_unb,valid_unb = canonical_smiles(generated_unb, sanitize=False, throw_warning=False) # validar 
        unique_smiles_unb = list(np.unique(sanitized_unb))[1:]
        
        #prediction kor
        prediction_kor_unb = self.predictor.predict(unique_smiles_unb)
        #prediction qed
        mol_list_unb = smiles2mol(unique_smiles_unb) 
        prediction_qed_unb = qed_calculator(mol_list_unb)
        
        if individual_plot:
            plot_hist(prediction_kor_unb,n_to_generate,valid_unb,"kor")
            plot_hist(prediction_qed_unb,n_to_generate,valid_unb,"qed")
            
        
        # Load Biased Generator Model 
        self.generator.model.load_weights(self.configReinforce.model_name_biased + "_" + self.scalarization_mode +  "_" + self.best_model + ".h5")
        print("\n --------- Updated model LOADED! ---------")
        
        generated_b = []
        pbar = tqdm(range(n_to_generate))
        for i in pbar:
            pbar.set_description("Generating molecules...")
            predictSMILES = PredictSMILES(self.generator,None,False,self.threshold_greedy,self.configReinforce)
            generated_b.append(predictSMILES.sample())
    
        sanitized_b,valid_b = canonical_smiles(generated_b, sanitize=False, throw_warning=False) # validar 
                
        san_with_repeated_b = []
        for smi in sanitized_b:
            if len(smi) > 1:
                san_with_repeated_b.append(smi)
        
        unique_smiles_b = list(np.unique(san_with_repeated_b))[1:]
        percentage_unq_b = (len(unique_smiles_b)/len(san_with_repeated_b))*100
        
#        unique_smiles_b = list(np.unique(sanitized_b))[1:]
        
        #prediction kor
        prediction_kor_b = self.predictor.predict(san_with_repeated_b)
        #prediction qed
        mol_list_b = smiles2mol(san_with_repeated_b) 
        prediction_qed_b = qed_calculator(mol_list_b)

        # plot both distributions together and compute the % of valid generated by the biased model 
        dif_qed, valid_qed = plot_hist_both(prediction_qed_unb,prediction_qed_b,n_to_generate,valid_unb,valid_b,"qed")
        dif_kor, valid_kor = plot_hist_both(prediction_kor_unb,prediction_kor_b,n_to_generate,valid_unb,valid_b,"kor")
        
        # Compute the internal diversity
        div = diversity(unique_smiles_b)
        
        return dif_qed,dif_kor,valid_kor,div,percentage_unq_b

    def drawMols(self):
        """
        Function that draws chemical graphs of compounds generated by the opmtized
        model.

        Parameters:
        -----------
        self: it contains the Generator and the configuration parameters

        Returns
        -------
        This function returns a figure with the specified number of molecular 
        graphs indicating the pIC50 for KOR and the QED.
        """
        DrawingOptions.atomLabelFontSize = 50
        DrawingOptions.dotsPerAngstrom = 100
        DrawingOptions.bondLineWidth = 3
                  
        self.generator.model.load_weights(self.configReinforce.model_name_biased + "_" + self.scalarization_mode + "_" + self.best_model+ ".h5")

        generated = []
        pbar = tqdm(range(self.configReinforce.n_to_generate))
        for i in pbar:
            pbar.set_description("Generating molecules...")
            predictSMILES = PredictSMILES(self.generator,None,False,self.threshold_greedy,self.configReinforce)
            generated.append(predictSMILES.sample())
    
        sanitized,valid = canonical_smiles(generated,sanitize=True, throw_warning=False) 
        
        unique_smiles = list(np.unique(sanitized))[1:]
        
        # prediction pIC50 KOR
        prediction_kor = self.predictor.predict(unique_smiles)
        
        # prediction qew
        mol_list = smiles2mol(unique_smiles)
        prediction_qed = qed_calculator(mol_list)
                
        ind = np.random.randint(0, len(mol_list), self.configReinforce.n_to_draw)
        mols_to_draw = [mol_list[i] for i in ind]
        
        legends = []
        for i in ind:
            legends.append('pIC50 for KOR: ' + str(round(prediction_kor[i],2)) + '|| QED: ' + str(round(prediction_qed[i],2)))
        
        img = Draw.MolsToGridImage(mols_to_draw, molsPerRow=1, subImgSize=(300,300), legends=legends)
            
        img.show()