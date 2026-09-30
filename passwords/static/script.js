// Keep the length slider and number box in sync.
const slider = document.getElementById("length-slider");
const lengthInput = document.getElementById("length");
slider.addEventListener("input", () => { lengthInput.value = slider.value; });
lengthInput.addEventListener("input", () => { slider.value = lengthInput.value; });

// Copy the generated password to the clipboard.
const copyBtn = document.getElementById("copy-btn");
if (copyBtn) {
  const passwordInput = document.getElementById("password");
  const status = document.getElementById("copy-status");

  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(passwordInput.value);
    } catch {
      // Fallback for browsers without the async Clipboard API.
      passwordInput.select();
      if (!document.execCommand("copy")) {
        status.textContent = "Couldn't copy — select the password and copy it manually.";
        return;
      }
    }
    copyBtn.textContent = "Copied!";
    status.textContent = "Password copied to clipboard.";
    setTimeout(() => {
      copyBtn.textContent = "Copy";
      status.textContent = "";
    }, 2000);
  });
}
