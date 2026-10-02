// Ask for confirmation before deleting a birthday.
document.querySelectorAll(".delete-form").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!confirm(`Delete ${form.dataset.name}'s birthday?`)) event.preventDefault();
  });
});
