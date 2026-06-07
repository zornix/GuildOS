"use client";
import { useState } from "react";
import { api } from "../../lib/api-client";
import { T } from "../../lib/theme";
import { Btn } from "../ui/btn";
import { Input } from "../ui/input";

interface CreateEventFormProps {
  onSuccess: () => void;
  onClose: () => void;
}

export function CreateEventForm({ onSuccess, onClose }: CreateEventFormProps) {
  const [f, setF] = useState({ title: "", date: "", time: "", location: "", required: true, fine_amount: 25 });

  const submit = async () => {
    if (!f.title || !f.date || !f.time) return;
    await api.createEvent(f);
    onSuccess();
  };

  return (
    <>
      <h3 style={{ margin: "0 0 16px", color: T.tx }}>Create Event</h3>
      <Input label="Title" value={f.title} onChange={(e) => setF((p) => ({ ...p, title: e.target.value }))} />
      <Input label="Date" type="date" value={f.date} onChange={(e) => setF((p) => ({ ...p, date: e.target.value }))} />
      <Input label="Time" type="time" value={f.time} onChange={(e) => setF((p) => ({ ...p, time: e.target.value }))} />
      <Input label="Location" value={f.location} onChange={(e) => setF((p) => ({ ...p, location: e.target.value }))} />
      <Input label="Fine Amount ($)" type="number" value={f.fine_amount} onChange={(e) => setF((p) => ({ ...p, fine_amount: +e.target.value }))} />
      <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: T.tx, marginBottom: 16 }}>
        <input type="checkbox" checked={f.required} onChange={(e) => setF((p) => ({ ...p, required: e.target.checked }))} /> Required event
      </label>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
        <Btn onClick={submit}>Create</Btn>
      </div>
    </>
  );
}
