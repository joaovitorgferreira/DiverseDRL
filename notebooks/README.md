## Step by step for running the model 

The [chemprop](https://github.com/chemprop/chemprop) is also installed.

To install the conda env:

```
conda env create -f environment.yml
```
To update the env:

```
conda env export | grep -v "^prefix: " > environment.yml
```

To run the notebooks:

```
conda activate diversedrl
jupyter notebook
```
