# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/70_callback.wandb.ipynb (unless otherwise specified).

__all__ = ['WandbCallback', 'log_dataset', 'log_model', 'wandb_process']

# Cell
from ..basics import *
from .progress import *
from ..text.data import TensorText
from ..tabular.all import TabularDataLoaders, Tabular
from .hook import total_params

# Cell
import wandb

# Cell
class WandbCallback(Callback):
    "Saves model topology, losses & metrics"
    remove_on_fetch,order = True,Recorder.order+1
    # Record if watch has been called previously (even in another instance)
    _wandb_watch_called = False

    def __init__(self, log="gradients", log_preds=True, log_model=True, log_dataset=False, dataset_name=None, valid_dl=None, n_preds=36, seed=12345, reorder=True):
        # Check if wandb.init has been called
        if wandb.run is None:
            raise ValueError('You must call wandb.init() before WandbCallback()')
        # W&B log step
        self._wandb_step = wandb.run.step - 1  # -1 except if the run has previously logged data (incremented at each batch)
        self._wandb_epoch = 0 if not(wandb.run.step) else math.ceil(wandb.run.summary['epoch']) # continue to next epoch
        store_attr('log,log_preds,log_model,log_dataset,dataset_name,valid_dl,n_preds,seed,reorder')

    def before_fit(self):
        "Call watch method to log model topology, gradients & weights"
        self.run = not hasattr(self.learn, 'lr_finder') and not hasattr(self, "gather_preds") and rank_distrib()==0
        if not self.run: return

        # Log config parameters
        log_config = self.learn.gather_args()
        _format_config(log_config)
#         try:
#             wandb.config.update(log_config, allow_val_change=True)
#         except Exception as e:
#             print(f'WandbCallback could not log config parameters -> {e}')

#         if not WandbCallback._wandb_watch_called:
#             WandbCallback._wandb_watch_called = True
#             # Logs model topology and optionally gradients and weights
#             wandb.watch(self.learn.model, log=self.log)

#         # log dataset
#         assert isinstance(self.log_dataset, (str, Path, bool)), 'log_dataset must be a path or a boolean'
#         if self.log_dataset is True:
#             if Path(self.dls.path) == Path('.'):
#                 print('WandbCallback could not retrieve the dataset path, please provide it explicitly to "log_dataset"')
#                 self.log_dataset = False
#             else:
#                 self.log_dataset = self.dls.path
#         if self.log_dataset:
#             self.log_dataset = Path(self.log_dataset)
#             assert self.log_dataset.is_dir(), f'log_dataset must be a valid directory: {self.log_dataset}'
#             metadata = {'path relative to learner': os.path.relpath(self.log_dataset, self.learn.path)}
#             log_dataset(path=self.log_dataset, name=self.dataset_name, metadata=metadata)

        # log model
        if self.log_model and not hasattr(self, 'save_model'):
            print('WandbCallback requires use of "SaveModelCallback" to log best model')
            self.log_model = False

        if self.log_preds:
            try:
                if not self.valid_dl:
                    #Initializes the batch watched
                    wandbRandom = random.Random(self.seed)  # For repeatability
                    self.n_preds = min(self.n_preds, len(self.dls.valid_ds))
                    idxs = wandbRandom.sample(range(len(self.dls.valid_ds)), self.n_preds)
                    if isinstance(self.dls,  TabularDataLoaders):
                        test_items = getattr(self.dls.valid_ds.items, 'iloc', self.dls.valid_ds.items)[idxs]
                        self.valid_dl = self.dls.test_dl(test_items, with_labels=True, process=False)
                    else:
                        test_items = [getattr(self.dls.valid_ds.items, 'iloc', self.dls.valid_ds.items)[i] for i in idxs]
                        self.valid_dl = self.dls.test_dl(test_items, with_labels=True)
                self.learn.add_cb(FetchPredsCallback(dl=self.valid_dl, with_input=True, with_decoded=True, reorder=self.reorder))
            except Exception as e:
                self.log_preds = False
                print(f'WandbCallback was not able to prepare a DataLoader for logging prediction samples -> {e}')

    def after_batch(self):
        return
        "Log hyper-parameters and training loss"
        if self.training:
            self._wandb_step += 1
            self._wandb_epoch += 1/self.n_iter
            hypers = {f'{k}_{i}':v for i,h in enumerate(self.opt.hypers) for k,v in h.items()}
            wandb.log({'epoch': self._wandb_epoch, 'train_loss': to_detach(self.smooth_loss.clone()), 'raw_loss': to_detach(self.loss.clone()), **hypers}, step=self._wandb_step)

    def log_predictions(self, preds):
        return
        inp,preds,targs,out = preds
        b = tuplify(inp) + tuplify(targs)
        x,y,its,outs = self.valid_dl.show_results(b, out, show=False, max_n=self.n_preds)
        wandb.log(wandb_process(x, y, its, outs), step=self._wandb_step)

    def after_epoch(self):
        "Log validation loss and custom metrics & log prediction samples"
        # Correct any epoch rounding error and overwrite value
        self._wandb_epoch = round(self._wandb_epoch)
        wandb.log({'epoch': self._wandb_epoch}, step=self._wandb_step)
        # Log sample predictions
        if self.log_preds:
            try:
                self.log_predictions(self.learn.fetch_preds.preds)
            except Exception as e:
                self.log_preds = False
                print(f'WandbCallback was not able to get prediction samples -> {e}')
        wandb.log({n:s for n,s in zip(self.recorder.metric_names, self.recorder.log) if n not in ['train_loss', 'epoch', 'time']}, step=self._wandb_step)

    def after_fit(self):
        return
        if self.log_model:
            if self.save_model.last_saved_path is None:
                print('WandbCallback could not retrieve a model to upload')
            else:
                metadata = {n:s for n,s in zip(self.recorder.metric_names, self.recorder.log) if n not in ['train_loss', 'epoch', 'time']}
                log_model(self.save_model.last_saved_path, metadata=metadata)
        self.run = True
        if self.log_preds: self.remove_cb(FetchPredsCallback)
        wandb.log({})  # ensure sync of last step
        self._wandb_step += 1

# Cell
@patch
def gather_args(self:Learner):
    "Gather config parameters accessible to the learner"
    # args stored by `store_attr`
    cb_args = {f'{cb}':getattr(cb,'__stored_args__',True) for cb in self.cbs}
    args = {'Learner':self, **cb_args}
    # input dimensions
    try:
        n_inp = self.dls.train.n_inp
        args['n_inp'] = n_inp
        xb = self.dls.train.one_batch()[:n_inp]
        args.update({f'input {n+1} dim {i+1}':d for n in range(n_inp) for i,d in enumerate(list(detuplify(xb[n]).shape))})
    except: pass#print(f'Could not gather input dimensions')
    # other useful information
    with ignore_exceptions():
        args['batch size'] = self.dls.bs
        args['batch per epoch'] = len(self.dls.train)
        args['model parameters'] = total_params(self.model)[0]
        args['device'] = self.dls.device.type
        args['frozen'] = bool(self.opt.frozen_idx)
        args['frozen idx'] = self.opt.frozen_idx
        args['dataset.tfms'] = f'{self.dls.dataset.tfms}'
        args['dls.after_item'] = f'{self.dls.after_item}'
        args['dls.before_batch'] = f'{self.dls.before_batch}'
        args['dls.after_batch'] = f'{self.dls.after_batch}'
    return args

# Cell
def _make_plt(img):
    "Make plot to image resolution"
    # from https://stackoverflow.com/a/13714915
    my_dpi = 100
    fig = plt.figure(frameon=False, dpi=my_dpi)
    h, w = img.shape[:2]
    fig.set_size_inches(w / my_dpi, h / my_dpi)
    ax = plt.Axes(fig, [0., 0., 1., 1.])
    ax.set_axis_off()
    fig.add_axes(ax)
    return fig, ax

# Cell
def _format_config_value(v):
    if isinstance(v, list):
        return [_format_config_value(item) for item in v]
    elif hasattr(v, '__stored_args__'):
        return {**_format_config(v.__stored_args__), '_name': v}
    return v

# Cell
def _format_config(config):
    "Format config parameters before logging them"
    for k,v in config.items():
        if isinstance(v, dict):
            config[k] = _format_config(v)
        else:
            config[k] = _format_config_value(v)
    return config

# Cell
def _format_metadata(metadata):
    "Format metadata associated to artifacts"
    for k,v in metadata.items(): metadata[k] = str(v)

# Cell
def log_dataset(path, name=None, metadata={}, description='raw dataset'):
    "Log dataset folder"
    # Check if wandb.init has been called in case datasets are logged manually
    if wandb.run is None:
        raise ValueError('You must call wandb.init() before log_dataset()')
    path = Path(path)
    if not path.is_dir():
        raise f'path must be a valid directory: {path}'
    name = ifnone(name, path.name)
    _format_metadata(metadata)
    artifact_dataset = wandb.Artifact(name=name, type='dataset', metadata=metadata, description=description)
    # log everything except "models" folder
    for p in path.ls():
        if p.is_dir():
            if p.name != 'models': artifact_dataset.add_dir(str(p.resolve()), name=p.name)
        else: artifact_dataset.add_file(str(p.resolve()))
    wandb.run.use_artifact(artifact_dataset)

# Cell
def log_model(path, name=None, metadata={}, description='trained model'):
    "Log model file"
    if wandb.run is None:
        raise ValueError('You must call wandb.init() before log_model()')
    path = Path(path)
    if not path.is_file():
        raise f'path must be a valid file: {path}'
    name = ifnone(name, f'run-{wandb.run.id}-model')
    _format_metadata(metadata)
    artifact_model = wandb.Artifact(name=name, type='model', metadata=metadata, description=description)
    with artifact_model.new_file(name, mode='wb') as fa:
        fa.write(path.read_bytes())
    wandb.run.log_artifact(artifact_model)

# Cell
@typedispatch
def wandb_process(x:TensorImage, y, samples, outs):
    "Process `sample` and `out` depending on the type of `x/y`"
    res_input, res_pred, res_label = [],[],[]
    for s,o in zip(samples, outs):
        img = s[0].permute(1,2,0)
        res_input.append(wandb.Image(img, caption='Input data'))
        for t, capt, res in ((o[0], "Prediction", res_pred), (s[1], "Ground Truth", res_label)):
            fig, ax = _make_plt(img)
            # Superimpose label or prediction to input image
            ax = img.show(ctx=ax)
            ax = t.show(ctx=ax)
            res.append(wandb.Image(fig, caption=capt))
            plt.close(fig)
    return {"Inputs":res_input, "Predictions":res_pred, "Ground Truth":res_label}

# Cell
@typedispatch
def wandb_process(x:TensorImage, y:(TensorCategory,TensorMultiCategory), samples, outs):
    return {"Prediction Samples": [wandb.Image(s[0].permute(1,2,0), caption=f'Ground Truth: {s[1]}\nPrediction: {o[0]}')
            for s,o in zip(samples,outs)]}

# Cell
@typedispatch
def wandb_process(x:TensorImage, y:TensorMask, samples, outs):
    res = []
    codes = getattr(y, 'codes', None)
    class_labels = {i:f'{c}' for i,c in enumerate(codes)} if codes is not None else None
    for s,o in zip(samples, outs):
        img = s[0].permute(1,2,0)
        masks = {}
        for t, capt in ((o[0], "Prediction"), (s[1], "Ground Truth")):
            masks[capt] = {'mask_data':t.numpy().astype(np.uint8)}
            if class_labels: masks[capt]['class_labels'] = class_labels
        res.append(wandb.Image(img, masks=masks))
    return {"Prediction Samples":res}

# Cell
@typedispatch
def wandb_process(x:TensorText, y:(TensorCategory,TensorMultiCategory), samples, outs):
    data = [[s[0], s[1], o[0]] for s,o in zip(samples,outs)]
    return {"Prediction Samples": wandb.Table(data=data, columns=["Text", "Target", "Prediction"])}

# Cell
@typedispatch
def wandb_process(x:Tabular, y:Tabular, samples, outs):
    df = x.all_cols
    for n in x.y_names: df[n+'_pred'] = y[n].values
    return {"Prediction Samples": wandb.Table(dataframe=df)}

# Cell
#nbdev_comment _all_ = ['wandb_process']
