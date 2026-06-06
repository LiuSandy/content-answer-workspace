import "@mdxeditor/editor/style.css";

import {
  BlockTypeSelect,
  BoldItalicUnderlineToggles,
  headingsPlugin,
  listsPlugin,
  ListsToggle,
  markdownShortcutPlugin,
  MDXEditor,
  type MDXEditorMethods,
  quotePlugin,
  Separator as MarkdownToolbarSeparator,
  thematicBreakPlugin,
  toolbarPlugin,
  UndoRedo,
} from "@mdxeditor/editor";
import { useEffect, useMemo, useRef } from "react";

import { cn } from "@/lib/utils";

type MarkdownEditorProps = {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  placeholder?: string;
};

function MarkdownEditor({ value, onChange, className, placeholder }: MarkdownEditorProps) {
  const editorRef = useRef<MDXEditorMethods>(null);
  const plugins = useMemo(
    () => [
      headingsPlugin({ allowedHeadingLevels: [2, 3, 4] }),
      listsPlugin(),
      quotePlugin(),
      thematicBreakPlugin(),
      markdownShortcutPlugin(),
      toolbarPlugin({
        toolbarContents: () => (
          <>
            <UndoRedo />
            <MarkdownToolbarSeparator />
            <BoldItalicUnderlineToggles />
            <MarkdownToolbarSeparator />
            <BlockTypeSelect />
            <ListsToggle />
          </>
        ),
      }),
    ],
    [],
  );

  useEffect(() => {
    const editor = editorRef.current;
    if (editor && editor.getMarkdown() !== value) {
      editor.setMarkdown(value);
    }
  }, [value]);

  return (
    <div className={cn("markdown-editor-shell", className)}>
      <MDXEditor
        ref={editorRef}
        markdown={value}
        onChange={onChange}
        placeholder={placeholder}
        plugins={plugins}
        className="markdown-editor"
        contentEditableClassName="markdown-editor__content"
      />
    </div>
  );
}

export { MarkdownEditor };
