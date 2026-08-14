import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    selectionHighlight: {
      /** 在指定范围画一个持久高亮装饰，不随编辑器失焦而消失 */
      setSelectionHighlight: (from: number, to: number) => ReturnType;
      /** 清除当前的持久高亮装饰 */
      clearSelectionHighlight: () => ReturnType;
    };
  }
}

type HighlightRange = { from: number; to: number } | null;

const selectionHighlightPluginKey = new PluginKey<HighlightRange>("selectionHighlight");

/**
 * 持久选区高亮扩展：局部优化对话框弹出后编辑器会失焦，浏览器原生选区渲染
 * 依赖 focus 状态，失焦后高亮会视觉消失（但选区位置数据仍在）。这里用
 * ProseMirror Decoration 独立画一层高亮，只受插件 state 控制，不受
 * focus/selection 影响，保证对话框打开期间用户选中的内容一直可见。
 */
export const SelectionHighlight = Extension.create({
  name: "selectionHighlight",

  addProseMirrorPlugins() {
    return [
      new Plugin<HighlightRange>({
        key: selectionHighlightPluginKey,
        state: {
          init() {
            return null;
          },
          apply(tr, value) {
            const meta = tr.getMeta(selectionHighlightPluginKey);
            if (meta !== undefined) {
              return meta;
            }
            if (value && tr.docChanged) {
              return { from: tr.mapping.map(value.from), to: tr.mapping.map(value.to) };
            }
            return value;
          },
        },
        props: {
          decorations(state) {
            const range = selectionHighlightPluginKey.getState(state);
            if (!range || range.from === range.to) return null;
            return DecorationSet.create(state.doc, [
              Decoration.inline(range.from, range.to, { class: "selection-highlight" }),
            ]);
          },
        },
      }),
    ];
  },

  addCommands() {
    return {
      setSelectionHighlight:
        (from: number, to: number) =>
        ({ tr, dispatch }) => {
          if (dispatch) {
            tr.setMeta(selectionHighlightPluginKey, { from, to });
          }
          return true;
        },
      clearSelectionHighlight:
        () =>
        ({ tr, dispatch }) => {
          if (dispatch) {
            tr.setMeta(selectionHighlightPluginKey, null);
          }
          return true;
        },
    };
  },
});
