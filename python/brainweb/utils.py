from __future__ import division
import numpy as np
from skimage.transform import resize
from skimage.filters import gaussian
from os import path
from glob import glob
import logging

__author__ = "Casper O. da Costa-Luis <casper.dcl@physics.org>"
__date__ = "2017-19"
__licence__ = __license__ = "[MPLv2.0](https://www.mozilla.org/MPL/2.0)"
__all__ = ["volshow", "noise", "toPetMmr", "get_files", "DATA_DIR"]

DATA_DIR = path.dirname(path.abspath(__file__))


def get_files(data_dir=DATA_DIR):
    """
    Returns list of files which can be `numpy.load`ed
    """
    return sorted(glob(path.join(DATA_DIR, 'subject_*.npz')))


def volshow(vol,
            cmaps=None, colorbars=None,
            xlabels=None, ylabels=None, titles=None,
            sharex=True, sharey=True):
    """
    Interactively slice through 3D array(s) in Jupyter

    @param vol  : 3darray or [3darray, ...] or {'title': 3darray, ...}
    @param cmaps  : list of cmap [default: ["Greys_r", ...]]
    @param xlabels, ylabels, titles  : list of strings (default blank)
    @param sharex, sharey  : passed to `matplotlib.pyplot.subplots`
    """
    import matplotlib.pyplot as plt
    import ipywidgets as ipyw

    if hasattr(vol, "keys") and hasattr(vol, "values"):
        if titles is not None:
            log.warn("ignoring `vol.keys()` in favour of specified `titles`")
        else:
            titles = vol.keys()
            vol = vol.values()

    if vol[0].ndim == 2:
        vol = [vol]
    else:
        assert vol[0].ndim == 3, "Input should be (one or a list of) 3D array(s)"

    if cmaps is None:
        cmaps = ["Greys_r"] * len(vol)
    if colorbars is None:
        colorbars = [False] * len(vol)
    if xlabels is None:
        xlabels = [""] * len(vol)
    if ylabels is None:
        ylabels = [""] * len(vol)
    if titles is None:
        titles = [""] * len(vol)

    cols = max(1, int(len(vol) ** 0.5))
    rows = int(np.ceil(len(vol) / cols))
    zSize = min(len(i) for i in vol)
    fig = plt.figure()

    @ipyw.interact(z=ipyw.IntSlider(zSize // 2, 0, zSize - 1, 1))
    def plot_slice(z):
        """z  : int, slice index"""
        plt.figure(fig.number)
        plt.clf()
        axs = fig.subplots(rows, cols, sharex=sharex, sharey=sharey)
        axs = getattr(axs, 'flat', [axs])
        for ax, v, cmap, cbar, xlab, ylab, tit in zip(axs, vol, cmaps, colorbars, xlabels, ylabels, titles):
            plt.sca(ax)
            plt.imshow(v[z], cmap=cmap)
            if cbar:
                plt.colorbar()
            if xlab:
                plt.xlabel(xlab)
            if ylab:
                plt.ylabel(ylab)
            if tit:
                plt.title(tit)
            plt.show()
        plt.tight_layout(0, 0, 0)
        #return fig, axs

    return plot_slice


class Act(object):
  """careful: occasionally other bits may be set"""
  background, csf, greyMatter, whiteMatter, fat, muscle, skin, skull, vessels,\
      aroundFat, dura, marrow\
      = [i << 4 for i in range(12)]
  bone = skull | marrow | dura

  @classmethod
  def indices(cls, im, attr):
    if attr == "bone":
      return (cls.indices(im, "skull") +
              cls.indices(im, "marrow") +
              cls.indices(im, "dura") > 0)
    return abs(im - getattr(cls, attr)) < 1


class Pet(Act):
  whiteMatter = 32
  greyMatter = whiteMatter * 4
  skin = whiteMatter // 2
  attrs = ["whiteMatter", "greyMatter", "skin"]


class T1(Act):
  whiteMatter = 154
  greyMatter = 106
  skin = 92
  skull = 48
  marrow = 180
  bone = 48
  csf = 48
  attrs = ["whiteMatter", "greyMatter", "skin", "skull", "marrow", "bone",
           "csf"]


class T2(T1):
  whiteMatter = 70
  greyMatter = 100
  skin = 70
  skull = 100
  marrow = 250
  csf = 250
  bone = 200


mu_bone_1_cm = 0.13
mu_tissue_1_cm = 0.0975


class Res(object):
  mMR = np.array([2.0312, 2.0863, 2.0863])
  MR = np.array([1.0, 1.0, 1.0])
  brainweb = np.array([0.5, 0.5, 0.5])


class Shape(object):
  mMR = np.array([127, 344, 344])
  MR = mMR * Res.mMR / Res.MR
  brainweb = mMR * Res.mMR / Res.brainweb


def getRaw(fname):
  """z, y, x"""
  return np.fromfile(fname, dtype=np.uint16).reshape((362, 434, 362))


def noise(im, n, warn_zero=True, sigma=1):
  """
  @param n  : float, noise fraction (0, inf)
  @param sigma  : float, smoothing of noise component
  @return[out] im  : array like im with +-n *100%im noise added
  """
  log = logging.getLogger(__name__)
  if n < 0:
    raise ValueError("Noise must be positive")
  elif n == 0:
    if warn_zero:
      log.warn("zero noise")
    return im
  r = gaussian(np.random.rand(*im.shape), sigma=sigma, multichannel=False)
  return im * (1 + n * (2 * r - 1))


def toPetMmr(im, pad=True, dtype=np.float32, outres="mMR"):
  """
  @return out  : [[PET, uMap, T1, T2], 127, 344, 344]
  """
  log = logging.getLogger(__name__)

  out_res = getattr(Res, outres)
  out_shape = getattr(Shape, outres)

  # PET
  # res = np.zeros(im.shape, dtype=dtype)
  res = np.zeros_like(im)
  for attr in Pet.attrs:
    log.debug("PET:%s:%d" % (attr, getattr(Pet, attr)))
    res[Act.indices(im, attr)] = getattr(Pet, attr)

  # muMap
  muMap = np.zeros(im.shape, dtype=dtype)
  muMap[im != 0] = mu_tissue_1_cm
  muMap[Act.indices(im, "bone")] = mu_bone_1_cm

  # MR
  # t1 = np.zeros(im.shape, dtype=dtype)
  t1 = np.zeros_like(im)
  for attr in T1.attrs:
    log.debug("T1:%s:%d" % (attr, getattr(T1, attr)))
    t1[Act.indices(im, attr)] = getattr(T1, attr)
  # t2 = np.zeros(im.shape, dtype=dtype)
  t2 = np.zeros_like(im)
  for attr in T2.attrs:
    log.debug("T2:%s:%d" % (attr, getattr(T2, attr)))
    t2[Act.indices(im, attr)] = getattr(T2, attr)

  # resize
  new_shape = np.rint(np.asarray(im.shape) * Res.brainweb / out_res)
  padLR, padR = divmod((np.array(out_shape) - new_shape), 2)

  def resizeToMmr(arr):
    # oldMax = arr.max()
    # arr = arr.astype(np.float32)
    # arr /= arr.max()
    arr = resize(arr, new_shape,
                 order=1, mode="constant", anti_aliasing=False)
    if pad:
      arr = np.pad(arr, [(p, p + r) for (p, r)
                         in zip(padLR.astype(int), padR.astype(int))],
                   mode="constant")
    if arr.dtype == np.uint16:
      return np.asarray(arr, dtype=np.float32) * np.float32(2 ** 16)
    return arr.astype(dtype)

  return [resizeToMmr(i) for i in [res, muMap, t1, t2]]


def matify(mat, dtype=np.float32, transpose=None):
  """@param transpose  : tuple<int>, (default: range(mat.ndim)[::-1])"""
  if transpose is None:
    transpose = tuple(range(mat.ndim)[::-1])
  return mat.transpose(transpose).astype(dtype)