import math
import torch
import numpy as np
import torch.nn as nn
from torch.autograd import Variable
import torch.nn.functional as F
from torch.nn import CrossEntropyLoss
from util import clones

class FAVORAttention(nn.Module):
  def __init__(self):
    pass

  def z_sin_cos(x, omega):
    pi = np.pi
    sin = lambda x: torch.sin(2 * pi * x)
    cos = lambda x: torch.cos(2 * pi * x)

    coef = torch.exp(x.pow(2).sum(dim=-1, keepdims=True) / 2)
    product = np.einsum("...d,rd->...r", x, omega)
    return coef * np.concatenate([sin(product), cos(product)], axis=-1)
  def forward(self):
    pass

class SelfAttention(nn.Module):
  def __init__(self):
    super(SelfAttention,self).__init__()
    self.matmul = torch.matmul
    self.softmax = torch.softmax

  def forward(self,query, key, value, mask=None):
    key_transpose = torch.transpose(key,-2,-1)          # (bath, head_num, d_k, token_)
    matmul_result = self.matmul(query,key_transpose)    # MatMul(Q,K)
    d_k = key.size()[-1]
    attention_score = matmul_result/math.sqrt(d_k)      # Scale

    if mask is not None:
      attention_score = attention_score.masked_fill(mask == 0, -1e20)

    softmax_attention_score = self.softmax(attention_score,dim=-1)                   # 어텐션 값
    result = self.matmul(softmax_attention_score,value)

    return result, softmax_attention_score

class MultiHeadAttention(nn.Module):
  def __init__(self, head_num =8 , d_model = 512,dropout = 0.1):
    super(MultiHeadAttention,self).__init__()

    self.head_num = head_num
    self.d_model = d_model
    self.d_k = self.d_v = d_model // head_num

    self.w_q = nn.Linear(d_model,d_model)
    self.w_k = nn.Linear(d_model,d_model)
    self.w_v = nn.Linear(d_model,d_model)
    self.w_o = nn.Linear(d_model,d_model)

    self.self_attention = SelfAttention()
    self.dropout = nn.Dropout(p=dropout)

  def forward(self, query, key, value, mask = None):
    if mask is not None:
      # Same mask applied to all h heads.
      mask = mask.unsqueeze(1)

    batche_num = query.size(0)

    query = self.w_q(query).view(batche_num, -1, self.head_num, self.d_k).transpose(1, 2)
    key = self.w_k(key).view(batche_num, -1, self.head_num, self.d_k).transpose(1, 2)
    value = self.w_v(value).view(batche_num, -1, self.head_num, self.d_k).transpose(1, 2)

    attention_result, attention_score = self.self_attention(query, key, value, mask)
    attention_result = attention_result.transpose(1,2).contiguous().view(batche_num, -1, self.head_num * self.d_k)

    return self.w_o(attention_result)

class FeedForward(nn.Module):
  def __init__(self,d_model, dropout = 0.1):
    super(FeedForward,self).__init__()
    self.w_1 = nn.Linear(d_model, d_model*4)
    self.w_2 = nn.Linear(d_model*4, d_model)
    self.dropout = nn.Dropout(p=dropout)

  def forward(self, x):
    return self.w_2(self.dropout(F.relu(self.w_1(x))))

class LayerNorm(nn.Module):
  def __init__(self, features, eps=1e-6):
    super(LayerNorm,self).__init__()
    self.a_2 = nn.Parameter(torch.ones(features))
    self.b_2 = nn.Parameter(torch.zeros(features))
    self.eps = eps
  def forward(self, x):
    mean = x.mean(-1, keepdim =True) # 평균
    std = x.std(-1, keepdim=True)    # 표준편차

    return self.a_2 * (x-mean)/ (std + self.eps) + self.b_2

class ResidualConnection(nn.Module):
  def __init__(self, size, dropout):
    super(ResidualConnection,self).__init__()
    self.norm = LayerNorm(size)
    self.dropout = nn.Dropout(dropout)

  def forward(self, x, sublayer):
    return x + self.dropout((sublayer(self.norm(x))))

class Encoder(nn.Module):
  def __init__(self, d_model, head_num, dropout):
    super(Encoder,self).__init__()
    self.multi_head_attention = MultiHeadAttention(d_model= d_model, head_num= head_num)
    self.residual_1 = ResidualConnection(d_model,dropout=dropout)

    self.feed_forward = FeedForward(d_model)
    self.residual_2 = ResidualConnection(d_model,dropout=dropout)

  def forward(self, input, mask):
    x = self.residual_1(input, lambda x: self.multi_head_attention(x, x, x, mask))
    x = self.residual_2(x, lambda x: self.feed_forward(x))
    return x

class Decoder(nn.Module):
  def __init__(self, d_model,head_num, dropout):
    super(Decoder,self).__init__()
    self.masked_multi_head_attention = MultiHeadAttention(d_model= d_model, head_num= head_num)
    self.residual_1 = ResidualConnection(d_model,dropout=dropout)

    self.encoder_decoder_attention = MultiHeadAttention(d_model= d_model, head_num= head_num)
    self.residual_2 = ResidualConnection(d_model,dropout=dropout)

    self.feed_forward= FeedForward(d_model)
    self.residual_3 = ResidualConnection(d_model,dropout=dropout)


  def forward(self, target, encoder_output, target_mask, encoder_mask):
    # target, x, target_mask, input_mask
    x = self.residual_1(target, lambda x: self.masked_multi_head_attention(x, x, x, target_mask))
    x = self.residual_2(x, lambda x: self.encoder_decoder_attention(x, encoder_output, encoder_output, encoder_mask))
    x = self.residual_3(x, self.feed_forward)

    return x

class Embeddings(nn.Module):
  def __init__(self, vocab_num, d_model):
    super(Embeddings,self).__init__()
    self.emb = nn.Embedding(vocab_num,d_model)
    self.d_model = d_model
  def forward(self, x):
    """
    1) 임베딩 값에 math.sqrt(self.d_model)을 곱해주는 이유는 무엇인지 찾아볼것
    2) nn.Embedding에 다시 한번 찾아볼것
    """
    return self.emb(x) * math.sqrt(self.d_model)

class PositionalEncoding(nn.Module):
  def __init__(self, max_seq_len, d_model,dropout=0.1):
    super(PositionalEncoding,self).__init__()
    self.dropout = nn.Dropout(p=dropout)

    pe = torch.zeros(max_seq_len, d_model)

    position = torch.arange(0,max_seq_len).unsqueeze(1)
    base = torch.ones(d_model//2).fill_(10000)
    pow_term = torch.arange(0, d_model, 2) / torch.tensor(d_model,dtype=torch.float32)
    div_term = torch.pow(base,pow_term)

    pe[:, 0::2] = torch.sin(position / div_term)
    pe[:, 1::2] = torch.cos(position / div_term)

    pe = pe.unsqueeze(0)

    # pe를 학습되지 않는 변수로 등록
    self.register_buffer('positional_encoding', pe)

  def forward(self, x):
    x = x + Variable(self.positional_encoding[:, :x.size(1)], requires_grad=False)
    return self.dropout(x)

class Generator(nn.Module):
  def __init__(self, d_model, vocab_num):
    super(Generator, self).__init__()
    self.proj_1 = nn.Linear(d_model, d_model*4)
    self.proj_2 = nn.Linear(d_model*4, vocab_num)

  def forward(self, x):
    x = self.proj_1(x)
    x = self.proj_2(x)
    return x

class Transformer(nn.Module):
  def __init__(self,vocab_num, d_model, max_seq_len, head_num, dropout, N):
    super(Transformer,self).__init__()
    self.embedding = Embeddings(vocab_num, d_model)
    self.positional_encoding = PositionalEncoding(max_seq_len,d_model)

    self.encoders = clones(Encoder(d_model=d_model, head_num=head_num, dropout=dropout), N)
    self.decoders = clones(Decoder(d_model=d_model, head_num=head_num, dropout=dropout), N)

    self.generator = Generator(d_model, vocab_num)

  def forward(self, input, target, input_mask, target_mask, labels=None):
      x = self.positional_encoding(self.embedding(input))
      for encoder in self.encoders:
        x = encoder(x, input_mask)

      target = self.positional_encoding(self.embedding(target))
      for decoder in self.decoders:
        # target, encoder_output, target_mask, encoder_mask)
        target = decoder(target, x, target_mask, input_mask)

      lm_logits = self.generator(target)
      loss = None
      if labels is not None:
        # Shift so that tokens < n predict n
        shift_logits = lm_logits[..., :-1, :].contiguous()
        shift_labels = labels[..., 1:].contiguous()
        # Flatten the tokens
        loss_fct = CrossEntropyLoss(ignore_index=0)
        loss = loss_fct(shift_logits.view(-1, shift_logits.size(-1)), shift_labels.view(-1))

      return lm_logits, loss
  def encode(self,input, input_mask):
    x = self.positional_encoding(self.embedding(input))
    for encoder in self.encoders:
      x = encoder(x, input_mask)
    return x

  def decode(self, encode_output, encoder_mask, target, target_mask):
    target = self.positional_encoding(self.embedding(target))
    for decoder in self.decoders:
      target = decoder(target, encode_output, target_mask, encoder_mask)

    lm_logits = self.generator(target)

    return lm_logits

if __name__=="__main__":
  pass
