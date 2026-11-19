export type User = { id: number; email: string; role: string; balance: number };
export type Item = {
  id: number;
  name: string;
  price: number;
  is_available: boolean;
  category_id: number | null;
  image_url?: string | null;
  description?: string;
  ingredients?: string[];
  dietary_tags?: string[];
  portion_value?: number | null;
  portion_unit?: string | null;
};
export type Category = { id: number; name: string };
export type Order = {
  id: number;
  item_id: number;
  quantity: number;
  total_cost: number;
  status: string;
  payment_source: string;
  created_at: string | null;
};
export type Payment = {
  id: string;
  order_id: number;
  amount: string;
  provider: string;
  status: string;
  confirmation_url: string | null;
  refund_status: string | null;
  review_required: boolean;
  cancellation_reason: string | null;
};
export type Delivery = {
  id: number;
  order_id: number;
  status: string;
  courier_id: number;
};
export type Source = { id: string; text: string; url: string };
export type Reply = {
  conversation_id: string;
  answer: string;
  available: boolean;
  sources: Source[];
  latency_ms: number;
};
