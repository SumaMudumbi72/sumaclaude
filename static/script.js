// Submit the toggle form as soon as a checkbox changes.
document.querySelectorAll(".toggle").forEach((checkbox) => {
  checkbox.addEventListener("change", () => checkbox.form.submit());
});

// Ask for confirmation before deleting a todo.
document.querySelectorAll(".delete-form").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!confirm("Delete this todo?")) event.preventDefault();
  });
});
