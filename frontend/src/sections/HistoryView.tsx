import { useEffect, useState, useMemo } from "react";
import { SectionShell } from "./SectionShell";
import { useCorvus } from "../state/store";
import { api, type Conversation } from "../lib/api";
import { Search, Trash2, Calendar, MessageSquare, ArrowDownAZ, CheckSquare, Square } from "lucide-react";

export function HistoryView() {
  const conversations = useCorvus((s) => s.conversations);
  const refresh = useCorvus((s) => s.refreshConversations);
  const open = useCorvus((s) => s.openConversation);
  const backendOnline = useCorvus((s) => s.backendOnline);

  const [search, setSearch] = useState("");
  const [sortOrder, setSortOrder] = useState<"Newest" | "Oldest">("Newest");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (backendOnline) void refresh();
  }, [backendOnline, refresh]);

  async function remove(id: number) {
    await api.deleteConversation(id);
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    await refresh();
  }

  async function removeSelected() {
    for (const id of selectedIds) {
      await api.deleteConversation(id);
    }
    setSelectedIds(new Set());
    await refresh();
  }

  function toggleSelection(id: number, e: React.MouseEvent) {
    e.stopPropagation();
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (selectedIds.size === filteredConversations.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredConversations.map((c) => c.id)));
    }
  }

  const filteredConversations = useMemo(() => {
    let result = conversations;
    if (search.trim()) {
      const lower = search.toLowerCase();
      result = result.filter((c) => c.title.toLowerCase().includes(lower));
    }
    return result.sort((a, b) => {
      const d1 = new Date(a.updated_at + "Z").getTime();
      const d2 = new Date(b.updated_at + "Z").getTime();
      return sortOrder === "Newest" ? d2 - d1 : d1 - d2;
    });
  }, [conversations, search, sortOrder]);

  const groupedConversations = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const lastWeek = new Date(today);
    lastWeek.setDate(lastWeek.getDate() - 7);

    const groups: { label: string; items: Conversation[] }[] = [
      { label: "Today", items: [] },
      { label: "Yesterday", items: [] },
      { label: "Previous 7 Days", items: [] },
      { label: "Older", items: [] },
    ];

    filteredConversations.forEach((c) => {
      const d = new Date(c.updated_at + "Z");
      if (d >= today) {
        groups[0].items.push(c);
      } else if (d >= yesterday) {
        groups[1].items.push(c);
      } else if (d >= lastWeek) {
        groups[2].items.push(c);
      } else {
        groups[3].items.push(c);
      }
    });

    return groups.filter((g) => g.items.length > 0);
  }, [filteredConversations]);

  return (
    <SectionShell title="History">
      <div className="flex h-full min-h-0 flex-col">
        {/* Toolbar */}
        <div className="flex flex-col gap-4 border-b border-white/5 pb-4 md:flex-row md:items-center md:justify-between px-6 pt-4">
          <div className="flex flex-1 items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 transition-all focus-within:border-white/30 focus-within:bg-white/10 focus-within:ring-2 focus-within:ring-white/10 max-w-md">
            <Search className="h-4 w-4 text-gray-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search conversations..."
              className="flex-1 bg-transparent text-sm font-medium text-white placeholder:font-normal placeholder:text-gray-500 outline-none"
            />
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setSortOrder(sortOrder === "Newest" ? "Oldest" : "Newest")}
              className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-white/10 hover:text-white"
            >
              <ArrowDownAZ className="h-4 w-4" />
              {sortOrder} First
            </button>
            {selectedIds.size > 0 && (
              <button
                onClick={() => void removeSelected()}
                className="flex items-center gap-2 rounded-lg bg-danger/20 px-3 py-2 text-sm font-medium text-danger transition-colors hover:bg-danger hover:text-white"
              >
                <Trash2 className="h-4 w-4" />
                Delete Selected ({selectedIds.size})
              </button>
            )}
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {conversations.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <MessageSquare className="h-12 w-12 text-gray-600 mb-4" />
              <h2 className="text-lg font-semibold text-white">No history yet</h2>
              <p className="mt-1 text-sm text-gray-400">Start a new conversation in the Chat tab.</p>
            </div>
          ) : filteredConversations.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <Search className="h-12 w-12 text-gray-600 mb-4" />
              <h2 className="text-lg font-semibold text-white">No results found</h2>
              <p className="mt-1 text-sm text-gray-400">Try adjusting your search query.</p>
            </div>
          ) : (
            <div className="space-y-6 max-w-4xl pb-10">
              {groupedConversations.map((group) => (
                <div key={group.label} className="space-y-2">
                  <div className="sticky top-0 z-10 flex items-center justify-between bg-black/95 py-2 backdrop-blur-md">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500">
                      {group.label}
                    </h3>
                    {group.label === groupedConversations[0].label && (
                      <button
                        onClick={toggleAll}
                        className="flex items-center gap-1.5 text-xs font-medium text-gray-400 hover:text-white transition-colors"
                      >
                        {selectedIds.size === filteredConversations.length ? (
                          <CheckSquare className="h-3.5 w-3.5" />
                        ) : (
                          <Square className="h-3.5 w-3.5" />
                        )}
                        Select All
                      </button>
                    )}
                  </div>
                  <div className="space-y-1">
                    {group.items.map((c) => {
                      const isSelected = selectedIds.has(c.id);
                      return (
                        <div
                          key={c.id}
                          className={`group flex items-center justify-between rounded-lg px-2 py-3 transition-all cursor-pointer ${
                            isSelected ? "bg-white/10" : "hover:bg-white/5"
                          }`}
                          onClick={() => void open(c.id)}
                        >
                          <div className="flex min-w-0 flex-1 items-center gap-4">
                            <button
                              onClick={(e) => toggleSelection(c.id, e)}
                              className="shrink-0 p-1 text-gray-500 hover:text-white transition-colors"
                            >
                              {isSelected ? (
                                <CheckSquare className="h-5 w-5 text-white" />
                              ) : (
                                <Square className="h-5 w-5" />
                              )}
                            </button>
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-sm font-semibold text-white">
                                {c.title}
                              </div>
                              <div className="flex items-center gap-1.5 text-xs font-medium text-gray-500 mt-0.5">
                                <Calendar className="h-3 w-3" />
                                {new Date(c.updated_at + "Z").toLocaleString(undefined, {
                                  month: "short",
                                  day: "numeric",
                                  hour: "numeric",
                                  minute: "numeric",
                                })}
                              </div>
                            </div>
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              void remove(c.id);
                            }}
                            className="shrink-0 rounded-lg p-2 text-gray-500 opacity-0 transition-all hover:bg-danger/20 hover:text-danger group-hover:opacity-100 focus:opacity-100 ml-4"
                            title="Delete Conversation"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </SectionShell>
  );
}
