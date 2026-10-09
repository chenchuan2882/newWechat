App({
  onLaunch() {
    if (!wx.cloud) {
      wx.showModal({
        title: "版本提示",
        content: "请更新微信后使用",
        showCancel: false,
      });
      return;
    }
    wx.cloud.init({ traceUser: true });
  },
});
