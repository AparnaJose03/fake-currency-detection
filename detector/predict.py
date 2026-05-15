import tensorflow as tf
import numpy as np
from tensorflow.keras.preprocessing import image
import os

MODEL_PATH = os.path.join(os.path.dirname(__file__), "efficientnet_b0_best.h5")

model = tf.keras.models.load_model(MODEL_PATH)

class_names = ["fake", "real"]

def predict_currency(img_path):

    img = image.load_img(img_path, target_size=(224,224))
    img_array = image.img_to_array(img)
    img_array = np.expand_dims(img_array, axis=0)

    preprocess = tf.keras.applications.efficientnet.preprocess_input
    img_array = preprocess(img_array)

    predictions = model.predict(img_array)

    predicted_class_idx = np.argmax(predictions[0])
    confidence = float(np.max(predictions[0]))
    class_scores = {
 
        "fake": float(predictions[0][0]),
        "real": float(predictions[0][1]),
    }

    return class_names[predicted_class_idx], confidence, class_scores
