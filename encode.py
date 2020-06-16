import numpy as np
import pathlib

curr_dir_path = str(pathlib.Path().absolute())
data_path = curr_dir_path + "/Data/"

def encode(seq):

    encoded_seq = np.zeros(len(seq)*4,int)
    for j in range(len(seq)):
        if seq[j] == 'A' or seq[j] == 'a':
            encoded_seq[j*4] = 1
            encoded_seq[j*4+1] = 0
            encoded_seq[j*4+2] = 0
            encoded_seq[j*4+3] = 0

        elif seq[j] == 'C' or seq[j] == 'c':
            encoded_seq[j*4] = 0
            encoded_seq[j*4+1] = 1
            encoded_seq[j*4+2] = 0
            encoded_seq[j*4+3] = 0

        elif seq[j] == 'G' or seq[j] == 'g':
            encoded_seq[j*4] = 0
            encoded_seq[j*4+1] = 0
            encoded_seq[j*4+2] = 1
            encoded_seq[j*4+3] = 0

        elif seq[j] == 'T' or seq[j] == 't':
            encoded_seq[j*4] = 0
            encoded_seq[j*4+1] = 0
            encoded_seq[j*4+2] = 0
            encoded_seq[j*4+3] = 1

        else:
            encoded_seq[j*4] = 0
            encoded_seq[j*4+1] = 0
            encoded_seq[j*4+2] = 0
            encoded_seq[j*4+3] = 0

    return encoded_seq

def main():
    
    i = 0
 
    encoded_f = open(data_path+'encoded_seq', 'w')
                    
    seq_file=open(data_path+'dna_seq_start').read().splitlines()
    for line in seq_file:
        seq = line
        encoded_seq = encode(seq)
        for base in encoded_seq:
            encoded_f.write(str(base))
            encoded_f.write("   ")
        encoded_f.write("\n")

        i=i+1
        print(i)

    encoded_f.close()

if __name__ =='__main__':
    main()
