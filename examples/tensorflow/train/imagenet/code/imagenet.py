import os

import vgg_preprocessing
import tensorflow as tf

_DEFAULT_IMAGE_SIZE = 224
_NUM_CHANNELS = 3
_LABEL_CLASSES = 1001

_FILE_SHUFFLE_BUFFER = 1024
_SHUFFLE_BUFFER = 1500

class ImagenetDataSet(object):
  """Imagenet data set
  """

  def __init__(self, data_dir, subset='train', use_distortion=True):
    self.data_dir = data_dir
    self.subset = subset
    self.use_distortion = use_distortion

  def filenames(self, is_training, data_dir):
    """Return filenames for dataset."""
    if is_training:
      return [
          os.path.join(data_dir, 'train-%05d-of-01024' % i)
          for i in range(1024)]
    else:
      return [
          os.path.join(data_dir, 'validation-%05d-of-00128' % i)
          for i in range(128)]

  def parser(self, value, is_training):
    """Parse an ImageNet record from `value`."""
    keys_to_features = {
        'image/encoded':
            tf.FixedLenFeature((), tf.string, default_value=''),
        'image/format':
            tf.FixedLenFeature((), tf.string, default_value='jpeg'),
        'image/class/label':
            tf.FixedLenFeature([], dtype=tf.int64, default_value=-1),
        'image/class/text':
            tf.FixedLenFeature([], dtype=tf.string, default_value=''),
        'image/object/bbox/xmin':
             tf.VarLenFeature(dtype=tf.float32),
        'image/object/bbox/ymin':
            tf.VarLenFeature(dtype=tf.float32),
        'image/object/bbox/xmax':
            tf.VarLenFeature(dtype=tf.float32),
        'image/object/bbox/ymax':
            tf.VarLenFeature(dtype=tf.float32),
        'image/object/class/label':
            tf.VarLenFeature(dtype=tf.int64),
    }

    parsed = tf.parse_single_example(value, keys_to_features)

    image = tf.image.decode_image(
        tf.reshape(parsed['image/encoded'], shape=[]),
        _NUM_CHANNELS)
    image = tf.image.convert_image_dtype(image, dtype=tf.float32)

    image = vgg_preprocessing.preprocess_image(
        image=image,
        output_height=_DEFAULT_IMAGE_SIZE,
        output_width=_DEFAULT_IMAGE_SIZE,
        is_training=is_training)

    label = tf.cast(
        tf.reshape(parsed['image/class/label'], shape=[]),
        dtype=tf.int32)

    return image, label #tf.one_hot(label, _LABEL_CLASSES)

  def make_batch(self, batch_size, is_training, num_shards, num_epochs=1):
    data_dir = self.data_dir
    shards_batch_size = int(batch_size / num_shards)
    """Input function which provides batches for train or eval."""
    dataset = tf.data.Dataset.from_tensor_slices(self.filenames(is_training, data_dir))

    if is_training:
      dataset = dataset.shuffle(buffer_size=(_FILE_SHUFFLE_BUFFER * num_shards))

    dataset = dataset.flat_map(tf.data.TFRecordDataset)
    dataset = dataset.map(lambda value: self.parser(value, is_training),
                        num_parallel_calls=(num_shards*4))
    dataset = dataset.prefetch(batch_size)

    if is_training:
      # When choosing shuffle buffer sizes, larger sizes result in better
      # randomness, while smaller sizes have better performance.
      dataset = dataset.shuffle(buffer_size=_SHUFFLE_BUFFER)

    # We call repeat after shuffling, rather than before, to prevent separate
    # epochs from blending together.
    dataset = dataset.repeat(num_epochs)
    dataset = dataset.batch(shards_batch_size)

    iterator = dataset.make_one_shot_iterator()
    feature_shards = [[] for i in range(num_shards)]
    label_shards = [[] for i in range(num_shards)]
    for i in range(num_shards):
      images, labels = iterator.get_next()
      feature_shards[i] = images
      label_shards[i] = labels

    feature_shards = [tf.stack(x) for x in feature_shards]
    label_shards = [tf.stack(x) for x in label_shards]
    return feature_shards, label_shards
