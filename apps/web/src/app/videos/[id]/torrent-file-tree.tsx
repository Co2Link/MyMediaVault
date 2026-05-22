import type { TorrentFileRead } from "@/lib/types";

type FileTreeNode = {
  children: Map<string, FileTreeNode>;
  file: TorrentFileRead | null;
  name: string;
};

export function createFileTree(files: TorrentFileRead[]) {
  const root: FileTreeNode = { children: new Map(), file: null, name: "" };

  for (const file of files) {
    const parts = file.path.split(/[\\/]+/).filter(Boolean);
    const pathParts = parts.length > 0 ? parts : [file.path];
    let current = root;

    for (const [index, part] of pathParts.entries()) {
      const existing = current.children.get(part);
      const next = existing ?? { children: new Map(), file: null, name: part };
      current.children.set(part, next);
      current = next;

      if (index === pathParts.length - 1) {
        current.file = file;
      }
    }
  }

  return root;
}

function sortedNodes(node: FileTreeNode) {
  return [...node.children.values()].sort((left, right) => {
    if (left.file && !right.file) return 1;
    if (!left.file && right.file) return -1;
    return left.name.localeCompare(right.name, undefined, { sensitivity: "base" });
  });
}

function formatFileSize(sizeBytes: number) {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 1,
    style: "unit",
    unit: "byte",
    unitDisplay: "narrow",
  }).format(sizeBytes);
}

export function TorrentFileTree({ node }: { node: FileTreeNode }) {
  return (
    <ul className="file-tree">
      {sortedNodes(node).map((child) => {
        const childNodes = sortedNodes(child);

        if (childNodes.length > 0) {
          return (
            <li className="file-tree-folder" key={child.name}>
              <details>
                <summary>{child.name}</summary>
                <TorrentFileTree node={child} />
              </details>
            </li>
          );
        }

        return (
          <li className="file-tree-file" key={child.file?.path ?? child.name}>
            <span>{child.name}</span>
            {child.file ? <span>{formatFileSize(child.file.sizeBytes)}</span> : null}
          </li>
        );
      })}
    </ul>
  );
}
