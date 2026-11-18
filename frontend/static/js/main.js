// Shared frontend behavior; actions remain ordinary Flask form submissions.
document.addEventListener("DOMContentLoaded", function () {
    function showError(field) {
        if (!field.id) return;
        var errorId = field.id + "_error";
        var error = document.getElementById(errorId);
        if (!error) {
            error = document.createElement("p");
            error.id = errorId;
            error.className = "field-error";
            error.setAttribute("aria-live", "polite");
            field.parentNode.appendChild(error);
            var describedBy = (field.getAttribute("aria-describedby") || "").split(" ").filter(Boolean);
            describedBy.push(errorId);
            field.setAttribute("aria-describedby", describedBy.join(" "));
        }
        error.textContent = field.validationMessage;
        field.setAttribute("aria-invalid", "true");
    }
    document.querySelectorAll("form").forEach(function (form) {
        var fields = form.querySelectorAll("input, select, textarea");
        var password = form.querySelector("[name='password']");
        var confirmation = form.querySelector("[name='confirm_password']");
        function validate() {
            fields.forEach(function (field) {
                field.setCustomValidity("");
                if (field.type === "tel" && field.value) {
                    var digits = field.value.replace(/\D/g, "");
                    if (!/^[+\d\s().-]+$/.test(field.value) || digits.length < 7 || digits.length > 15) {
                        field.setCustomValidity("Enter a phone number with 7 to 15 digits.");
                    }
                }
                if (field.required && ["text", "textarea"].includes(field.type) && field.value && !field.value.trim()) {
                    field.setCustomValidity("Enter a value using more than spaces.");
                }
            });
            if (password && confirmation && password.value !== confirmation.value) {
                confirmation.setCustomValidity("Passwords do not match.");
            }
            form.querySelectorAll("[data-delivery-group]").forEach(function (group) {
                var boxes = Array.from(group.querySelectorAll("input[type='checkbox']"));
                if (boxes.length) boxes[0].setCustomValidity(boxes.some(function (box) { return box.checked; }) ? "" : "Choose at least one delivery method.");
            });
            fields.forEach(function (field) {
                if (field.validity.valid) {
                    field.removeAttribute("aria-invalid");
                    var error = document.getElementById(field.id + "_error");
                    if (error) error.textContent = "";
                }
            });
        }
        form.addEventListener("input", validate);
        form.addEventListener("change", validate);
        form.addEventListener("invalid", function (event) { showError(event.target); }, true);
        form.addEventListener("submit", function (event) {
            validate();
            if (!form.checkValidity()) {
                event.preventDefault();
                form.reportValidity();
                return;
            }
            var button = event.submitter;
            var message = button && button.getAttribute("data-confirm");
            if (form.hasAttribute("data-confirm-assignment")) {
                var selected = form.querySelector("select[name='org_id']").selectedOptions[0];
                message = "Assign " + form.getAttribute("data-confirm-assignment") + " to " + selected.textContent.trim() + "? Current organization: " + form.getAttribute("data-current-org") + ".";
            }
            if (message && !window.confirm(message)) event.preventDefault();
        });
        validate();
    });
    var priority = document.getElementById("priority");
    var priorityHelp = document.getElementById("priority_help");
    if (priority && priorityHelp) {
        function showPriorityText() {
            var option = priority.selectedOptions[0];
            var hours = option && option.getAttribute("data-hours");
            priorityHelp.textContent = hours ? "Response window: " + hours + " hours." : "";
        }
        priority.setAttribute("aria-describedby", "priority_help");
        priority.addEventListener("change", showPriorityText);
        showPriorityText();
    }
    var service = document.getElementById("service_id");
    var delivery = document.getElementById("delivery_method");
    var area = document.getElementById("service_area");
    if (service && delivery) {
        function updateDelivery() {
            var option = service.selectedOptions[0];
            var previous = delivery.value || delivery.getAttribute("data-selected");
            var methods = option ? JSON.parse(option.getAttribute("data-delivery") || "[]") : [];
            delivery.replaceChildren();
            if (!methods.length) delivery.add(new Option("Choose a service first", ""));
            methods.forEach(function (method) { delivery.add(new Option(method, method)); });
            if (methods.includes(previous)) delivery.value = previous;
            delivery.removeAttribute("data-selected");
            if (area) area.textContent = option && option.value ? "Service area: " + option.getAttribute("data-area") + "." : "";
        }
        service.addEventListener("change", updateDelivery);
        updateDelivery();
    }
    if (window.location.hash.startsWith("#request-")) {
        var row = document.getElementById(window.location.hash.slice(1));
        var details = row && row.nextElementSibling && row.nextElementSibling.querySelector("details");
        if (details) details.open = true;
    }
});
