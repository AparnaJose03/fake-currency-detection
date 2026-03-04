import os
from PIL import Image
import tensorflow as tf

# ===============================
# STEP 1 — REMOVE CORRUPTED IMAGES
# ===============================
def check_corrupted_images(folder):
    for root, dirs, files in os.walk(folder):
        for file in files:
            path = os.path.join(root, file)
            try:
                Image.open(path).verify()
            except:
                print("Corrupted:", path)
                os.remove(path)

check_corrupted_images("dataset/train")
check_corrupted_images("dataset/valid")
check_corrupted_images("dataset/test")


# ===============================
# STEP 2 — RESIZE IMAGES TO 224x224
# ===============================
def resize_images(folder, size=(224, 224)):
    for root, dirs, files in os.walk(folder):
        for file in files:
            path = os.path.join(root, file)
            try:
                img = Image.open(path).convert("RGB")
                img = img.resize(size)
                img.save(path)
            except:
                pass

resize_images("dataset/train")
resize_images("dataset/valid")
resize_images("dataset/test")


# ===============================
# STEP 3 — LOAD DATASETS (REPLACES ImageDataGenerator)
# ===============================
train_ds = tf.keras.utils.image_dataset_from_directory(
    "dataset/train",
    labels="inferred",
    label_mode="categorical",
    image_size=(224, 224),
    batch_size=32,
    shuffle=True
)

valid_ds = tf.keras.utils.image_dataset_from_directory(
    "dataset/valid",
    labels="inferred",
    label_mode="categorical",
    image_size=(224, 224),
    batch_size=32,
    shuffle=False
)

test_ds = tf.keras.utils.image_dataset_from_directory(
    "dataset/test",
    labels="inferred",
    label_mode="categorical",
    image_size=(224, 224),
    batch_size=32,
    shuffle=False
)


# ===============================
# STEP 4 — DATA AUGMENTATION (KERAS 3 STYLE)
# ===============================
data_augmentation = tf.keras.Sequential([
    tf.keras.layers.RandomRotation(0.05),
    tf.keras.layers.RandomZoom(0.10),
    tf.keras.layers.RandomBrightness(0.20),
    tf.keras.layers.RandomTranslation(0.1, 0.1),
])

train_ds = train_ds.map(lambda x, y: (data_augmentation(x, training=True), y))


# ===============================
# STEP 5 — EFFICIENTNET PREPROCESSING
# ===============================
preprocess = tf.keras.applications.efficientnet.preprocess_input

train_ds = train_ds.map(lambda x, y: (preprocess(x), y))
valid_ds = valid_ds.map(lambda x, y: (preprocess(x), y))
test_ds = test_ds.map(lambda x, y: (preprocess(x), y))


print("Preprocessing completed successfully!")
