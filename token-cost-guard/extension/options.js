chrome.storage.sync.get({ pollInterval: 5 }, (data) => {
  document.getElementById("interval").value = data.pollInterval ?? 5;
});

document.getElementById("save").addEventListener("click", () => {
  const val = parseInt(document.getElementById("interval").value, 10);
  const interval = Number.isFinite(val) && val >= 1 ? Math.min(val, 60) : 5;
  chrome.storage.sync.set({ pollInterval: interval }, () => {
    document.getElementById("saved").style.display = "block";
    setTimeout(() => { document.getElementById("saved").style.display = "none"; }, 2500);
  });
});
