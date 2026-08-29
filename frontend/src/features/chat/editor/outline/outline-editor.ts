export interface EditableOutlineSection {
  id?: string;
  order?: number;
  heading: string;
  keyPoints: string[];
  wordCountEstimate: number;
}

export function addSection(sections: EditableOutlineSection[]): EditableOutlineSection[] {
  return [
    ...sections,
    {
      heading: "新章节",
      keyPoints: ["新要点"],
      wordCountEstimate: 200,
    },
  ];
}

export function removeSection(
  sections: EditableOutlineSection[],
  index: number,
): EditableOutlineSection[] {
  if (sections.length <= 1) return sections;
  return sections.filter((_, sectionIndex) => sectionIndex !== index);
}

export function updateSection(
  sections: EditableOutlineSection[],
  index: number,
  patch: Partial<EditableOutlineSection>,
): EditableOutlineSection[] {
  return sections.map((section, sectionIndex) =>
    sectionIndex === index ? { ...section, ...patch } : section,
  );
}

export function addKeyPoint(
  sections: EditableOutlineSection[],
  sectionIndex: number,
): EditableOutlineSection[] {
  const section = sections[sectionIndex];
  if (!section) return sections;
  return updateSection(sections, sectionIndex, {
    keyPoints: [...section.keyPoints, "新要点"],
  });
}

export function removeKeyPoint(
  sections: EditableOutlineSection[],
  sectionIndex: number,
  keyPointIndex: number,
): EditableOutlineSection[] {
  const section = sections[sectionIndex];
  if (!section) return sections;
  return updateSection(sections, sectionIndex, {
    keyPoints: section.keyPoints.filter((_, index) => index !== keyPointIndex),
  });
}
