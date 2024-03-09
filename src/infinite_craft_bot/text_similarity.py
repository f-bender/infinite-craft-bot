import logging
from itertools import chain
from math import ceil

import numpy as np
import torch
from more_itertools import chunked
from scipy.spatial.distance import cosine
from transformers import AutoModel, AutoTokenizer

from infinite_craft_bot.logging_helpers import LogElapsedTime

logger = logging.getLogger(__name__)


class TextSimilarityCalculator:
    def __init__(self, device: str = "cuda", batch_size: int = 32) -> None:
        self.device = device
        self.batch_size = batch_size
        self.tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/bert-base-nli-mean-tokens")
        self.model = AutoModel.from_pretrained("sentence-transformers/bert-base-nli-mean-tokens").to(self.device)

    def compute_embeddings(self, texts: list[str]) -> list[np.ndarray]:
        with LogElapsedTime(logger.debug, label=f"Computing {len(texts)} embeddings"):
            embeddings: list[np.ndarray] = []
            for idx, text_batch in enumerate(chunked(texts, self.batch_size)):
                if idx % 10 == 0:
                    logger.debug(f"Computing embeddings: batch {idx + 1}/{ceil(len(texts)/self.batch_size)}")
                inputs = self._generate_model_inputs(text_batch)
                outputs = self.model(**inputs)
                embeddings += self._get_embedding_from_model_output(
                    outputs=outputs, attention_mask=inputs["attention_mask"]
                )

            return embeddings

    def _generate_model_inputs(self, texts: list[str]) -> dict[str, torch.Tensor]:
        tokenized_texts: dict[str, list[torch.Tensor]] = {"input_ids": [], "attention_mask": []}

        for sentence in texts:
            new_token = self.tokenizer.encode_plus(
                sentence, max_length=128, truncation=True, padding="max_length", return_tensors="pt"
            )
            tokenized_texts["input_ids"].append(new_token["input_ids"][0])  # type: ignore
            tokenized_texts["attention_mask"].append(new_token["attention_mask"][0])  # type: ignore

        return {key: torch.stack(value).to(self.device) for key, value in tokenized_texts.items()}

    @staticmethod
    def _get_embedding_from_model_output(outputs, attention_mask: torch.Tensor) -> np.ndarray:
        embeddings = outputs.last_hidden_state

        mask = attention_mask.unsqueeze(-1).expand(embeddings.size()).float()
        mask_embeddings = embeddings * mask

        # Then we sum the remained of the embeddings along axis 1:
        summed = torch.sum(mask_embeddings, 1)

        # Then sum the number of values that must be given attention in each position of the tensor:
        summed_mask = torch.clamp(mask.sum(1), min=1e-9)

        mean_pooled = summed / summed_mask
        mean_pooled = mean_pooled.detach().cpu().numpy()

        return list(mean_pooled)  # type: ignore

    @staticmethod
    def similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        # TODO in the future: allow passing an array where many similarities are computed at once
        return float(1 - cosine(embedding1, embedding2))
