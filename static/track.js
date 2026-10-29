// 広告リンクのクリックを GA4 イベント affiliate_click として送る（GA4 未設定なら何もしない）
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-offer]");
  if (a && typeof gtag === "function") {
    gtag("event", "affiliate_click", { offer: a.dataset.offer, page: location.pathname });
  }
});
