Component({
  properties: { post: Object },
  methods: {
    open() {
      this.triggerEvent("open", { id: this.data.post.id });
    },
    like() {
      this.triggerEvent("like", { post: this.data.post });
    },
    collect() {
      this.triggerEvent("collect", { post: this.data.post });
    },
    author() {
      this.triggerEvent("author", { id: this.data.post.author.id });
    },
  },
});
