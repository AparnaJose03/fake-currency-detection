/* =========================
   REGISTER
========================= */
const registerForm = document.getElementById("registerForm");
if (registerForm) {
    registerForm.addEventListener("submit", (e) => {
        e.preventDefault();

        const user = {
            name: document.getElementById("name").value,
            email: document.getElementById("email").value,
            phone: document.getElementById("phone").value,
            password: document.getElementById("password").value
        };

        localStorage.setItem("user", JSON.stringify(user));
        alert("Registration successful. Please login.");
        window.location.href = "login.html";
    });
}

/* =========================
   LOGIN
========================= */
const loginForm = document.getElementById("loginForm");
if (loginForm) {
    loginForm.addEventListener("submit", (e) => {
        e.preventDefault();

        const email = document.getElementById("email").value;
        const password = document.getElementById("password").value;

        const user = JSON.parse(localStorage.getItem("user"));

        if (!user || user.email !== email || user.password !== password) {
            alert("Invalid login credentials");
            return;
        }

        localStorage.setItem("isLoggedIn", "true");
        window.location.href = "index.html";
    });
}

/* =========================
   IMAGE UPLOAD
========================= */
// Elements
const uploadInput = document.getElementById("currencyImage");
const uploadBtn = document.getElementById("uploadBtn");
const resultDiv = document.getElementById("result"); // optional, to show result on page

// Upload function
async function uploadImage(file) {
    const formData = new FormData();
    formData.append("image", file);

    try {
        const response = await fetch("http://127.0.0.1:8000/api/detect/", {
            method: "POST",
            body: formData
        });

        if (!response.ok) {
            throw new Error("Network response was not ok");
        }

        const data = await response.json();

        // Show result in alert or on page
        const message = `Result: ${data.result}\nConfidence: ${(data.confidence * 100).toFixed(2)}%`;
        alert(message);

        if (resultDiv) {
            resultDiv.innerText = message;
        }

    } catch (error) {
        console.error("Error uploading image:", error);
        alert("Failed to upload image. See console for details.");
    }
}

// Connect button to function
if (uploadBtn && uploadInput) {
    uploadBtn.addEventListener("click", () => {
        // Check if logged in
        if (localStorage.getItem("isLoggedIn") !== "true") {
            alert("Please login first to upload images.");
            return;
        }

        const file = uploadInput.files[0];
        if (!file) {
            alert("Please select an image first!");
            return;
        }

        uploadImage(file);
    });
}