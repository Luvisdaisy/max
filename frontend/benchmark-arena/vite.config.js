/** Vite 配置：显式保留 Vue 运行时模板编译能力。 */
import { defineConfig } from "vite";

export default defineConfig({
  resolve: {
    alias: {
      vue: "vue/dist/vue.esm-bundler.js",
    },
  },
});
