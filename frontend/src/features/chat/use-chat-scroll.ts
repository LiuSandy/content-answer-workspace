import { useCallback, useEffect, useRef, useState } from "react";

export function useChatScroll(activeLeafMessageId: string | null) {
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  const isUserScrolledUpRef = useRef(false);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    if (viewportRef.current) {
      viewportRef.current.scrollTo({
        top: viewportRef.current.scrollHeight,
        behavior,
      });
      return;
    }
    messagesEndRef.current?.scrollIntoView({ behavior });
  }, []);

  const resetScrollTracking = useCallback(() => {
    isUserScrolledUpRef.current = false;
    setIsUserScrolledUp(false);
  }, []);

  const handleScrollCapture = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const viewport = event.target as HTMLDivElement;
    viewportRef.current = viewport;
    const distanceFromBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
    const scrolledUp = distanceFromBottom > 80;
    isUserScrolledUpRef.current = scrolledUp;
    setIsUserScrolledUp((current) => current === scrolledUp ? current : scrolledUp);
  }, []);

  const handleStreamingContentChange = useCallback(() => {
    if (!isUserScrolledUpRef.current) scrollToBottom("auto");
  }, [scrollToBottom]);

  const resumeAutoScroll = useCallback(() => {
    resetScrollTracking();
    scrollToBottom("smooth");
  }, [resetScrollTracking, scrollToBottom]);

  useEffect(() => {
    resumeAutoScroll();
  }, [activeLeafMessageId, resumeAutoScroll]);

  return {
    isUserScrolledUp,
    messagesEndRef,
    handleScrollCapture,
    handleStreamingContentChange,
    resetScrollTracking,
    resumeAutoScroll,
  };
}
