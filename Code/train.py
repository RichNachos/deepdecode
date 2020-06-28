from tqdm import tqdm
import os
import shutil
import numpy as np
import pandas as pd
from models import *
from metrics import *
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torch.autograd import Variable
import torch.utils.tensorboard as tb
import json
import pathlib
import time
from train_utils import *

curr_dir_path = str(pathlib.Path().absolute())
data_path = curr_dir_path + "/Data/"

class Training():

    def __init__(self, config, model_name_save_dir, data_path='', save_dir = '', start_epoch=0):
        self.config = config
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        self.data_path = data_path
        self.save_dir = save_dir

        self.start_epoch = start_epoch
        self.model = None
        self.optimizer = None
        self.trainloader = None

        self.metrics = {'train': {}, 'val': {}}
        self.model_name_save_dir = model_name_save_dir


    def save_checkpoint(self, epoch, save_best=False):
        """
        Saving checkpoints

        :param epoch: current epoch number
        :param log: logging information of the epoch
        :param save_best: if True, rename the saved checkpoint to 'model_best.pth'
        """
        state = {
            #'arch': arch,
            'epoch': epoch,
            'state_dict': self.model.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            #'monitor_best': self.mnt_best,
            'config': self.config
        }

        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
        filename = self.save_dir + str('/checkpoint-epoch{}.pth'.format(epoch))
        torch.save(state, filename)
        print("Saving checkpoint: {} ...".format(filename))
        if save_best:
            best_path = str(self.save_dir + 'model_best.pth')
            torch.save(state, best_path)
            print("Saving current best: model_best.pth ...")

    def resume_checkpoint(self, resume_path):
        """
        Resume from saved checkpoints

        :param resume_path: Checkpoint path to be resumed
        """
        resume_path = str(resume_path)
        print("Loading checkpoint: {} ...".format(resume_path))
        checkpoint = torch.load(resume_path)
        self.start_epoch = checkpoint['epoch'] + 1
        #self.mnt_best = checkpoint['monitor_best']

        # load architecture params from checkpoint.
        if checkpoint['config']['arch'] != self.config['arch']:
            self.logger.warning("Warning: Architecture configuration given in config file is different from that of "
                                "checkpoint. This may yield an exception while state_dict is being loaded.")
        self.model.load_state_dict(checkpoint['state_dict'])

        # load optimizer state from checkpoint only when optimizer type is not changed.
        if checkpoint['config']['optimizer']['type'] != self.config['optimizer']['type']:
            self.logger.warning("Warning: Optimizer type given in config file is different from that of checkpoint. "
                                "Optimizer parameters not being resumed.")
        else:
            self.optimizer.load_state_dict(checkpoint['optimizer'])

        self.logger.info("Checkpoint loaded. Resume training from epoch {}".format(self.start_epoch))

    def write_model_meta_data(self):
        '''
        Write meta-info about model to file
        '''
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)

        with open(self.save_dir+'/config.json', 'w') as outfile1:
            json.dump(self.config, outfile1, indent = 4)


        log_file = open(self.save_dir + '/info.log', "w+")
        log_file.write(str(self.model))
        log_file.close()

        #Todo: print to file
        print('Parameters')
        for name, param in self.model.named_parameters():
            if param.requires_grad:
                print(name, param.data.shape)

    '''
    def load_saved_state(self, state_file_path):
        global_step = 0
        start_batch = 0
        start_epoch = 0

        # Continue training from a saved serialised model.
        if state_file_path is not None:
            if not os.path.isfile(state_file_path):
                raise Exception("Failed to read path %s, aborting." % state_file_path)
                return
            state = torch.load(state_file_path)
            if len(state) != 5:
                raise Exception(
                    "Invalid state read from path %s, aborting. State keys: %s" % (state_file_path, state.keys()))
                return
            #Todo: understand Also to this log file, write model name and parameters
            global_step = state[SERIALISATION_KEY_GLOBAL_STEP]
            start_epoch = state[SERIALISATION_KEY_EPOCH]
            self.model.load_state_dict(state[SERIALISATION_KEY_MODEL])
            self.optimizer.load_state_dict(state[SERIALISATION_KEY_OPTIM])

            print("Loaded saved state successfully:")
            print("- Upcoming epoch: %d." % start_epoch)
            print("Resuming training...")
            return global_step, start_batch, start_epoch
    '''

    def logger(self, epoch, x_train, train_loss, val_loss):
        """
        Write to TensorBoard
        :param epoch: int - epoch number
        :param train_loss: float
        :param val_loss: float
        :return: None
        """

        tb_path = './runs/' + self.model_name_save_dir
        print('tb_path', tb_path)
        if os.path.isdir(tb_path):
            shutil.rmtree(tb_path)

        writer = tb.SummaryWriter(log_dir=tb_path+'/train')
        val_writer = tb.SummaryWriter(log_dir=tb_path + '/val')
        sample_data = iter(self.trainloader).next()[0]  # [batch_size X seq_length X embedding_dim]
        writer.add_graph(self.model, sample_data.to(self.device))
        writer.add_text('Model:', str(self.model))
        writer.add_text('Input shape:', str(x_train.shape))
        writer.add_text('Data Preprocessing:', 'None, One-hot')
        writer.add_text('Optimiser', str(self.optimizer))
        writer.add_text('Batch Size:', str(self.config['DATA']['BATCH_SIZE']))

        for measure, value in self.metrics['train'].items():
            writer.add_scalar(str('Train/'+measure), value, epoch)
        writer.add_scalar('Loss', train_loss, epoch)
        for measure, value in self.metrics['val'].items():
            val_writer.add_scalar(str('Val/'+measure), value, epoch)
        val_writer.add_scalar('Loss', val_loss, epoch)


    def train_one_epoch(self, epoch, x_train, y_train):

        # INPUT DATA
        trainset = SequenceDataset(x_train, y_train)  # NOTE: change input dataset size here if required
        self.trainloader = torch.utils.data.DataLoader(
                        trainset, batch_size=self.config['DATA']['BATCH_SIZE'],
                        shuffle=self.config['DATA']['SHUFFLE'], num_workers=self.config['DATA']['NUM_WORKERS'])

        # MODEL
        self.model = eval(self.config['MODEL_NAME'])(self.config['MODEL']['embedding_dim'], self.config['MODEL']['hidden_dim'],
                                                self.config['MODEL']['hidden_layers'], self.config['MODEL']['output_dim'],
                                                self.config['DATA']['BATCH_SIZE'], self.device)
        self.model.to(self.device)

        # LOSS FUNCTION
        loss_fn = getattr(nn, self.config['LOSS'])()  # For eg: nn.CrossEntropyLoss()

        # OPTIMISER  #todo: read from config file
        # optimiser = optim.SGD(model.parameters(), momentum=0.9, lr=0.001)
        self.optimizer = optim.RMSprop(self.model.parameters(), lr=0.1)

        avg_train_loss = 0
        m = Metrics(self.config['DATASET_TYPE'])   #m.metrics initialised to {0,0,0}
        self.metrics['train'] = m.metrics

        # FOR EACH BATCH
        for bnum, sample in tqdm(enumerate(self.trainloader)):
            self.model.train()
            self.model.zero_grad()
            print('Train batch: ', bnum)
            raw_out = self.model.forward(sample[0].to(self.device))
            loss = loss_fn(raw_out, sample[1].long().to(self.device))
            print('Loss: ', loss)
            loss.backward()
            self.optimizer.step()

            # EVALUATION METRICS PER BATCH
            metrics_for_batch = m.get_metrics(raw_out.detach().clone(), sample[1].detach().clone(), 'macro')  # todo: understand 'macro'
            for key,value in metrics_for_batch.items():
                self.metrics['train'][key] += value
            avg_train_loss += loss.item()

        # EVALUATION METRICS PER EPOCH
        for measure in m.metrics:
            self.metrics['train'][measure] /= (bnum+1)
        print('Epoch: {:d}, Train Loss: {:.4f}, '.format(epoch, avg_train_loss), self.metrics['train'])
        return avg_train_loss

    def val_one_epoch(self, epoch, x_val, y_val):

        trainset = SequenceDataset(x_val, y_val)  # NOTE: change input dataset size here if required todo:
        valdataloader = torch.utils.data.DataLoader(
                    trainset, batch_size=self.config['DATA']['BATCH_SIZE'],
                    shuffle=self.config['DATA']['SHUFFLE'], num_workers=self.config['DATA']['NUM_WORKERS'])

        m = Metrics(self.config['DATASET_TYPE'])  # m.metrics initialised to {0,0,0}
        self.metrics['val'] = m.metrics
        loss_fn =  getattr(nn, self.config['LOSS'])()
        avg_val_loss = 0
        for bnum, sample in enumerate(valdataloader):
            print('Val batch: ', bnum)
            self.model.eval()
            raw_out = self.model.forward(sample[0].to(self.device))
            loss = loss_fn(raw_out, sample[1].long().to(self.device))

            # EVALUATION METRICS PER BATCH
            metrics_for_batch = m.get_metrics(raw_out.detach().clone(), sample[1].detach().clone(), 'macro')
            for key, value in metrics_for_batch.items():
                self.metrics['val'][key] += value
            avg_val_loss += loss.item()

        print('Epoch: {:d}, Valid Loss: {:.4f}, '.format(epoch, avg_val_loss), self.metrics['val'])
        return avg_val_loss

    def training_pipeline(self):
        #Todo:For loading state, self.start epoch would change

        encoded_seq = np.loadtxt(self.data_path + '/encoded_seq')
        no_timesteps = int(len(encoded_seq[0]) / 4)
        encoded_seq = encoded_seq.reshape(-1, no_timesteps, 4)
        print("Input data shape: ", encoded_seq.shape)
        y_label = np.loadtxt(self.data_path + '/y_label_start')


        if self.config['VALIDATION']:
            train_idx, val_idx = create_train_val_split(self.config['DATA']['VALIDATION_SPLIT'], n_samples=len(encoded_seq))
            self.config['DATA']['SHUFFLE'] = False  # turn off shuffle option which is mutually exclusive with sampler

            print('len(train_idx)', len(train_idx))

            # Create train/validation split --
            x_train = encoded_seq[np.ix_(train_idx)] #replace `train_idx` by `np.arange(len(encoded_seq))` to use whole dataset
            y_train = y_label[np.ix_(train_idx)]
            x_val = encoded_seq[np.ix_(val_idx)]
            y_val = y_label[np.ix_(val_idx)]
        else:
            x_train = encoded_seq
            y_train = y_label

        print(x_train.shape, x_val.shape)

        for epoch in range(self.start_epoch, self.config['TRAINER']['epochs']):
            print("Training Epoch %i -------------------" % epoch)

            epoch_tic = time.time()
            train_loss = self.train_one_epoch(epoch, x_train, y_train)
            if self.config['VALIDATION']:
                val_loss = self.val_one_epoch(epoch, x_val, y_val)
            epoch_toc = time.time()
            epoch_time = epoch_toc - epoch_tic
            print("******************* Epoch %i completed in %i seconds ********************" % (epoch, epoch_time))

            # SAVE TO CHECKPOINT TO DIRECTORY
            if epoch==0:
                self.write_model_meta_data()
            if epoch % self.config['TRAINER']['save_period'] == 0:
                #self.write_model_loss_metrics()  # todo future: save to training file : epoch details loss, metrics etc.
                self.save_checkpoint(epoch)

            if self.config['TRAINER']['tensorboard']:
                if not self.config['VALIDATION']:
                    val_loss = 0.0
                self.logger(epoch, x_train, train_loss, val_loss)
                # write to runs folder (create a model file name, and write the various training runs in it

            # SAVE MODEL TO DIRECTORY
            torch.save(self.model, self.save_dir+'/trained_model_'+self.model_name_save_dir)

if __name__ == "__main__":

    chrm =  "chrm21/"

    # Get config file
    with open(curr_dir_path + "/config.json", encoding='utf-8', errors='ignore') as json_data:
        config = json.load(json_data, strict=False)

    final_data_path = data_path+chrm+config['DATASET_TYPE']+config["DATA"]["DATA_DIR"]
    saved_model_folder = string_metadata(config)
    save_dir_path = curr_dir_path + config['TRAINER']['save_dir'] + '/'+ saved_model_folder
    obj = Training(config,  saved_model_folder, final_data_path, save_dir_path)
    obj.training_pipeline()
