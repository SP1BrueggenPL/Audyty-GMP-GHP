function wireFormsetAdd(addBtnId, templateId, containerId, totalFormsName) {
  document.addEventListener("DOMContentLoaded", function () {
    var addBtn = document.getElementById(addBtnId);
    var tpl = document.getElementById(templateId);
    var container = document.getElementById(containerId);
    var totalInput = document.querySelector('input[name="' + totalFormsName + '"]');
    if (!addBtn || !tpl || !container || !totalInput) return;

    addBtn.addEventListener("click", function () {
      var index = parseInt(totalInput.value, 10);
      var html = tpl.innerHTML.replace(/__prefix__/g, index);
      var wrapper = document.createElement("tbody");
      wrapper.innerHTML = html;
      container.appendChild(wrapper.firstElementChild);
      totalInput.value = index + 1;
    });
  });
}
