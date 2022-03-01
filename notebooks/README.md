## Step by step for running the model 

To install the conda env:

```
conda env create -f environment.yml
```
To update the env:

```
conda env export | grep -v "^prefix: " > environment.yml
```
