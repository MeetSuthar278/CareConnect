// Shared catalog details are display-only; the server validates the selected IDs.
document.addEventListener('DOMContentLoaded',function () {
  const form=document.getElementById('add-service-form');
  if (!form) return;
  const service=form.querySelector('[name="service_id"]');
  function showCatalog() {
    const choice=service.selectedOptions[0];
    form.querySelector('#category_new').value=choice?.dataset.category || '';
    form.querySelector('#description_new').value=choice?.dataset.description || '';
    const labels={'in-person':'In person',online:'Online',phone:'Phone'};
    form.querySelectorAll('[name="delivery_methods"]').forEach(box => {
      box.checked=box.value===labels[choice?.dataset.delivery];
    });
  }
  service.addEventListener('change',showCatalog);
  showCatalog();
});
